import asyncio
import io
import discord
from discord import app_commands
from discord.ext import commands

import storage
import upi_utils

# --- Modal Form for Slot Configuration ---
class SlotConfigModal(discord.ui.Modal):
    def __init__(self, slot_id: int, current_upi: str = "", current_name: str = ""):
        super().__init__(title=f"Configure UPI Slot {slot_id}")
        self.slot_id = slot_id

        self.upi_input = discord.ui.TextInput(
            label=f"UPI ID / VPA for Slot {slot_id}:",
            placeholder="e.g. merchant@okicici or 9876543210@paytm",
            default=current_upi,
            required=True,
            max_length=100
        )
        self.add_item(self.upi_input)

        self.name_input = discord.ui.TextInput(
            label="Payee / Shop Name (Optional):",
            placeholder="e.g. John Store or Personal UPI",
            default=current_name if current_name and not current_name.startswith("Slot") else "",
            required=False,
            max_length=100
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            upi_id = self.upi_input.value.strip()
            name = self.name_input.value.strip()

            if not upi_utils.is_valid_upi(upi_id):
                await interaction.response.send_message(
                    "⚠️ **Invalid UPI ID format!** Please enter a valid UPI ID (e.g. `user@bank` or `9876543210@paytm`).",
                    ephemeral=True
                )
                return

            storage.update_slot(interaction.user.id, self.slot_id, upi_id, name or f"UPI Slot {self.slot_id}")

            embed = discord.Embed(
                title=f"✅ Slot {self.slot_id} Saved Successfully!",
                color=discord.Color.green()
            )
            embed.add_field(name="💳 UPI ID", value=f"`{upi_id}`", inline=True)
            embed.add_field(name="👤 Payee Name", value=f"`{name or f'UPI Slot {self.slot_id}'}`", inline=True)
            embed.set_footer(text="Now run /qr to generate custom payment QR codes!")

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error in SlotConfigModal: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

# --- Modal Form for Custom Amount ---
class CustomAmountModal(discord.ui.Modal):
    def __init__(self, slot_id: int):
        super().__init__(title="Enter Custom Payment Amount")
        self.slot_id = slot_id

        self.amount_input = discord.ui.TextInput(
            label="Amount in ₹ (e.g. 300 or 500.50):",
            placeholder="300",
            required=True,
            max_length=15
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt_str = self.amount_input.value.strip()
            formatted_amt = upi_utils.format_amount(amt_str)

            if not formatted_amt:
                await interaction.response.send_message("⚠️ Invalid amount specified. Enter a valid positive number like 300.", ephemeral=True)
                return

            await send_discord_qr(interaction, self.slot_id, formatted_amt)
        except Exception as e:
            print(f"Error in CustomAmountModal: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

# --- Interactive View for /upi-set (Slot Buttons) ---
class UpiSetView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        profile = storage.get_user_profile(user_id)

        for slot in profile.get("slots", []):
            slot_id = slot["id"]
            upi_id = slot.get("upiId", "")
            name = slot.get("name", f"Slot {slot_id}")

            is_set = bool(upi_id)
            label = f"Slot {slot_id}: {name}" if is_set else f"Set Slot {slot_id}"
            style = discord.ButtonStyle.success if is_set else discord.ButtonStyle.primary

            button = discord.ui.Button(
                label=label[:80],
                style=style,
                custom_id=f"btn_slot_{slot_id}"
            )
            button.callback = self.make_slot_callback(slot_id, upi_id, name)
            self.add_item(button)

    def make_slot_callback(self, slot_id, upi_id, name):
        async def callback(interaction: discord.Interaction):
            try:
                modal = SlotConfigModal(slot_id, current_upi=upi_id, current_name=name)
                await interaction.response.send_modal(modal)
            except Exception as e:
                print(f"Error launching slot modal: {e}")
        return callback

# --- Interactive Select Menu View for /qr (Select Slot) ---
class QrSlotSelectView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        configured = storage.get_configured_slots(user_id)

        options = [
            discord.SelectOption(
                label=f"Slot {s['id']}: {s['name']}",
                description=s['upiId'][:50],
                value=str(s['id']),
                emoji="💳"
            )
            for s in configured
        ]

        select = discord.ui.Select(
            placeholder="Choose a UPI ID slot...",
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        try:
            slot_id = int(interaction.data["values"][0])
            view = AmountSelectView(interaction.user.id, slot_id)

            profile = storage.get_user_profile(interaction.user.id)
            slot = next((s for s in profile["slots"] if s["id"] == slot_id), None)

            embed = discord.Embed(
                title="💰 Select Amount for QR Code",
                description=f"💳 **Selected Payee:** `{slot['name']}` (`{slot['upiId']}`)\n\nClick a quick amount button below or enter a custom amount:",
                color=discord.Color.blue()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        except Exception as e:
            print(f"Error in select_callback: {e}")

# --- Interactive Buttons View for Amount Selection ---
class AmountSelectView(discord.ui.View):
    def __init__(self, user_id, slot_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.slot_id = slot_id

        amounts = [50, 100, 200, 300, 500, 1000, 2000]

        for amt in amounts:
            btn = discord.ui.Button(
                label=f"₹{amt}",
                style=discord.ButtonStyle.green if amt == 300 else discord.ButtonStyle.secondary,
                custom_id=f"amt_{amt}"
            )
            btn.callback = self.make_amount_callback(amt)
            self.add_item(btn)

        custom_btn = discord.ui.Button(
            label="✏️ Custom Amount",
            style=discord.ButtonStyle.danger,
            custom_id="amt_custom"
        )
        custom_btn.callback = self.custom_amount_callback
        self.add_item(custom_btn)

    def make_amount_callback(self, amount):
        async def callback(interaction: discord.Interaction):
            await send_discord_qr(interaction, self.slot_id, str(amount))
        return callback

    async def custom_amount_callback(self, interaction: discord.Interaction):
        try:
            modal = CustomAmountModal(self.slot_id)
            await interaction.response.send_modal(modal)
        except Exception as e:
            print(f"Error launching custom amount modal: {e}")

# --- Helper function to render & send QR code ---
async def send_discord_qr(interaction: discord.Interaction, slot_id: int, amount: str):
    try:
        profile = storage.get_user_profile(interaction.user.id)
        slot = next((s for s in profile["slots"] if s["id"] == slot_id), None)

        if not slot or not slot.get("upiId"):
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Selected slot is missing a UPI ID.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Selected slot is missing a UPI ID.", ephemeral=True)
            return

        if not interaction.response.is_done():
            await interaction.response.defer()

        upi_id = slot["upiId"]
        payee_name = slot.get("name", "Payee")

        upi_url = upi_utils.build_upi_url(upi_id, amount, payee_name, f"Payment of Rs {amount}")
        qr_bytes = upi_utils.generate_qr_bytes(upi_url)

        file = discord.File(io.BytesIO(qr_bytes), filename=f"upi_qr_{amount}.png")

        embed = discord.Embed(
            title="⚡ Custom Value UPI QR Generated",
            color=discord.Color.green()
        )
        embed.add_field(name="💵 Amount", value=f"**₹{amount}**", inline=True)
        embed.add_field(name="💳 UPI ID", value=f"`{upi_id}`", inline=True)
        embed.add_field(name="👤 Payee Name", value=f"`{payee_name}`", inline=True)
        embed.set_image(url=f"attachment://upi_qr_{amount}.png")
        embed.set_footer(text="Scan with GPay, PhonePe, Paytm, BHIM, Cred or any UPI app to pay!")

        await interaction.followup.send(embed=embed, file=file)
    except Exception as e:
        print(f"Error in send_discord_qr: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Error generating QR: {e}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Error generating QR: {e}", ephemeral=True)

# --- Discord Bot Client Setup ---
class UpiBotClient(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Discord Slash Commands synced globally!")

bot_client = None

def create_bot_client():
    global bot_client
    bot_client = UpiBotClient()

    @bot_client.event
    async def on_ready():
        print(f"🤖 Logged in as Discord Bot: {bot_client.user} (ID: {bot_client.user.id})")
        await bot_client.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="₹ Custom Value QR | /qr"))

    @bot_client.tree.command(name="upi-set", description="Configure your 4 UPI ID slots using popup modals")
    async def upi_set_slash(interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚙️ Multi-Slot UPI ID Manager",
            description="Store up to **4 UPI IDs**. Click any button below to configure or edit that slot using a pop-up modal menu:",
            color=discord.Color.blurple()
        )
        profile = storage.get_user_profile(interaction.user.id)
        for s in profile.get("slots", []):
            status = "✅" if s.get("upiId") else "❌"
            val = f"💳 `{s['upiId']}`\n👤 *{s['name']}*" if s.get("upiId") else "*Not Configured*"
            embed.add_field(name=f"Slot {s['id']} {status}", value=val, inline=True)

        view = UpiSetView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    @bot_client.tree.command(name="qr", description="Generate a custom valued UPI QR Code (e.g. ₹300)")
    async def qr_slash(interaction: discord.Interaction):
        configured = storage.get_configured_slots(interaction.user.id)
        if not configured:
            embed = discord.Embed(
                title="⚠️ No UPI IDs Configured Yet!",
                description="Please configure at least 1 UPI ID slot before generating QR codes.\nUse `/upi-set` to get started!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="📱 Select UPI Slot for Custom QR",
            description="Choose which saved UPI ID you want to receive payment into:",
            color=discord.Color.blurple()
        )
        view = QrSlotSelectView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    @bot_client.tree.command(name="myupi", description="View your configured UPI ID slots")
    async def myupi_slash(interaction: discord.Interaction):
        profile = storage.get_user_profile(interaction.user.id)
        embed = discord.Embed(title="💳 Your Stored UPI ID Slots", color=discord.Color.blue())
        for s in profile.get("slots", []):
            val = f"`{s['upiId']}` ({s['name']})" if s.get("upiId") else "*Not Configured*"
            embed.add_field(name=f"Slot {s['id']}", value=val, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot_client.tree.command(name="help", description="Learn how to use the Custom UPI QR Bot")
    async def help_slash(interaction: discord.Interaction):
        embed = discord.Embed(
            title="ℹ️ Custom UPI QR Discord Bot Help",
            description=(
                "1️⃣ Run `/upi-set` to open the slot configuration pop-up menu.\n"
                "2️⃣ Choose Slot 1, 2, 3, or 4 and type your UPI ID in the modal form.\n"
                "3️⃣ Run `/qr` to pick your UPI ID and select an amount (e.g. ₹300).\n"
                "4️⃣ Or type any number directly in chat (e.g. `300`) to generate your payment QR code!"
            ),
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot_client.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return

        content = message.content.strip()

        if content.lower().startswith('!upi set') or content.lower().startswith('!upiset'):
            embed = discord.Embed(
                title="⚙️ Multi-Slot UPI ID Manager",
                description="Use slash command `/upi-set` to open interactive pop-up modals!",
                color=discord.Color.blurple()
            )
            view = UpiSetView(message.author.id)
            await message.channel.send(embed=embed, view=view)
            return

        if content.lower().startswith('!qr'):
            await message.channel.send("📱 Please type `/qr` as a slash command to open the interactive slot selector!")
            return

        # Direct number entry (e.g. typing "300" or "₹300")
        extracted_amt = upi_utils.format_amount(content)
        if extracted_amt and not " " in content:
            configured = storage.get_configured_slots(message.author.id)
            if not configured:
                await message.reply("💡 You entered an amount, but no UPI ID is saved yet! Use `/upi-set` to save your UPI ID first.")
            elif len(configured) == 1:
                upi_url = upi_utils.build_upi_url(configured[0]["upiId"], extracted_amt, configured[0]["name"])
                qr_bytes = upi_utils.generate_qr_bytes(upi_url)
                file = discord.File(io.BytesIO(qr_bytes), filename=f"upi_qr_{extracted_amt}.png")

                embed = discord.Embed(title="⚡ Custom Value UPI QR Generated", color=discord.Color.green())
                embed.add_field(name="💵 Amount", value=f"**₹{extracted_amt}**", inline=True)
                embed.add_field(name="💳 UPI ID", value=f"`{configured[0]['upiId']}`", inline=True)
                embed.set_image(url=f"attachment://upi_qr_{extracted_amt}.png")

                await message.reply(embed=embed, file=file)
            else:
                embed = discord.Embed(
                    title=f"💸 Select UPI Slot for ₹{extracted_amt}",
                    description="Which UPI ID slot should receive this payment?",
                    color=discord.Color.blue()
                )
                view = QrSlotSelectView(message.author.id)
                await message.reply(embed=embed, view=view)

    return bot_client
