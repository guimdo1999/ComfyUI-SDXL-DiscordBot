import discord
import discord.ext
from discord import app_commands
import configparser
import os
from PIL import Image
from datetime import datetime
from math import ceil, sqrt

def setup_config():
    if not os.path.exists('config.properties'):
        generate_default_config()

    if not os.path.exists('./out'):
        os.makedirs('./out')

    config = configparser.ConfigParser()
    config.read('config.properties')
    return config['BOT']['TOKEN'], config['BOT']['SDXL_SOURCE']

def generate_default_config():
    config = configparser.ConfigParser()
    config['DISCORD'] = {
        'TOKEN': 'YOUR_DEFAULT_DISCORD_BOT_TOKEN'
    }
    config['LOCAL'] = {
        'SERVER_ADDRESS': 'YOUR_COMFYUI_URL'
    }
    config['API'] = {
        'API_KEY': 'STABILITY_AI_API_KEY',
        'API_HOST': 'https://api.stability.ai',
        'API_IMAGE_ENGINE': 'STABILITY_AI_IMAGE_GEN_MODEL'
    }
    with open('config.properties', 'w') as configfile:
        config.write(configfile)

def create_collage(images):
    num_images = len(images)
    num_cols = ceil(sqrt(num_images))
    num_rows = ceil(num_images / num_cols)
    collage_width = max(image.width for image in images) * num_cols
    collage_height = max(image.height for image in images) * num_rows
    collage = Image.new('RGB', (collage_width, collage_height))

    for idx, image in enumerate(images):
        row = idx // num_cols
        col = idx % num_cols
        x_offset = col * image.width
        y_offset = row * image.height
        collage.paste(image, (x_offset, y_offset))

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    collage_path = f"./out/images_{timestamp}.png"
    collage.save(collage_path)

    return collage_path

# setting up the bot
TOKEN, IMAGE_SOURCE = setup_config()
intents = discord.Intents.default() 
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

if IMAGE_SOURCE == "LOCAL":
    from imageGen import generate_images, upscale_image, generate_alternatives
elif IMAGE_SOURCE == "API":
    from apiImageGen import generate_images, upscale_image, generate_alternatives

# sync the slash command to your server
@client.event
async def on_ready():
    await tree.sync()
    print(f'Logado como {client.user.name} ({client.user.id})')

class ImageButton(discord.ui.Button):
    def __init__(self, label, emoji, row, callback):
        super().__init__(label=label, style=discord.ButtonStyle.grey, emoji=emoji, row=row)
        self._callback = callback

    async def callback(self, interaction: discord.Interaction):
        await self._callback(interaction, self)


class Buttons(discord.ui.View):
    def __init__(self, prompt, negative_prompt, images, *, timeout=180):
        super().__init__(timeout=timeout)
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.images = images

        # Limite de botões do Discord é 25. Vamos limitar as imagens a 4 por segurança para caber tudo (Get, V, U + Reroll)
        if len(images) > 8:
            images = images[:8]

        # Row 0 = Botão Re-roll (definido no decorator lá embaixo)
        # Vamos definir as linhas explicitamente para ficar organizado:
        # Row 1 = Botões de Pegar Imagem Única (1, 2, 3, 4)
        # Row 2 = Botões de Variação (V1, V2, V3, V4)
        # Row 3 = Botões de Upscale (U1, U2, U3, U4)
        
        # 1. Botões para PEGAR IMAGEM ÚNICA (📩) - Row 1
        for idx, _ in enumerate(images):
            # Calcula a linha caso tenha mais de 5 imagens, mas geralmente ficará na row 1
            row = 1 + (idx // 5) 
            btn = ImageButton(f"{idx + 1}", "📩", row, self.enviar_imagem_unica)
            self.add_item(btn)

        # 2. Botões de VARIAÇÃO (V) - Row 2 (ou 3 se tivermos muitas imagens)
        for idx, _ in enumerate(images):
            # Adiciona offset para não ficar na mesma linha dos botões de pegar imagem
            row = 2 + (idx // 5) 
            btn = ImageButton(f"V{idx + 1}", "♻️", row, self.generate_alternatives_and_send)
            self.add_item(btn)

        # 3. Botões de UPSCALE (U) - Row 3 (ou 4 se tivermos muitas imagens)
        for idx, _ in enumerate(images):
            row = 3 + (idx // 5)
            # Proteção para não estourar o limite de 5 linhas (0 a 4) do Discord
            if row > 4: row = 4 
            btn = ImageButton(f"U{idx + 1}", "⬆️", row, self.upscale_and_send)
            self.add_item(btn)

    # --- NOVA FUNÇÃO: Envia apenas a imagem selecionada ---
    async def enviar_imagem_unica(self, interaction, button):
        # O label do botão é apenas o número "1", "2", etc.
        index = int(button.label) - 1 
        
        await interaction.response.send_message(f"Separando a imagem {button.label}, um momento...", ephemeral=True)
        
        image = self.images[index]
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        # Salva temporariamente
        single_image_path = f"./out/single_{timestamp}_{index}.png"
        image.save(single_image_path)
        
        # Envia para o canal
        msg_content = f"{interaction.user.mention} aqui está a imagem **{button.label}** separada."
        await interaction.channel.send(content=msg_content, file=discord.File(fp=single_image_path, filename=f'imagem_{button.label}.png'))

    async def generate_alternatives_and_send(self, interaction, button):
        index = int(button.label[1:]) - 1 
        await interaction.response.send_message("Criando alternativas, vamos lá...")
        images = await generate_alternatives(self.images[index], self.prompt, self.negative_prompt)
        collage_path = create_collage(images)
        final_message = f"{interaction.user.mention} aqui está algumas alternativas..."
        await interaction.channel.send(content=final_message, file=discord.File(fp=collage_path, filename='collage.png'), view=Buttons(self.prompt, self.negative_prompt, images))

    async def upscale_and_send(self, interaction, button):
        index = int(button.label[1:]) - 1
        await interaction.response.send_message("Upscaling...")
        upscaled_image = await upscale_image(self.images[index], self.prompt, self.negative_prompt)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        upscaled_image_path = f"./out/upscaledImage_{timestamp}.png"
        upscaled_image.save(upscaled_image_path)
        final_message = f"{interaction.user.mention} aqui está sua imagem em upscale."
        await interaction.channel.send(content=final_message, file=discord.File(fp=upscaled_image_path, filename='upscaled_image.png'))

    @discord.ui.button(label="Re-roll", style=discord.ButtonStyle.green, emoji="🎲", row=0)
    async def reroll_image(self, interaction, btn):
        await interaction.response.send_message(f"{interaction.user.mention} me pediu pare re-criar \"{self.prompt}\", vamos lá...")
        btn.disabled = True
        await interaction.message.edit(view=self)
        images = await generate_images(self.prompt,self.negative_prompt)

        final_message = f"{interaction.user.mention} me pediu para criar \"{self.prompt}\", aqui o que fiz."
        await interaction.channel.send(content=final_message, file=discord.File(fp=create_collage(images), filename='collage.png'), view = Buttons(self.prompt,self.negative_prompt,images))

    async def generate_alternatives_and_send(self, interaction, button):
        index = int(button.label[1:]) - 1  # Extract index from label
        await interaction.response.send_message("Criando alternativas, vamos lá...")
        images = await generate_alternatives(self.images[index], self.prompt, self.negative_prompt)
        collage_path = create_collage(images)
        final_message = f"{interaction.user.mention} aqui está algumas alternativas..."
        await interaction.channel.send(content=final_message, file=discord.File(fp=collage_path, filename='collage.png'), view=Buttons(self.prompt, self.negative_prompt, images))

    async def upscale_and_send(self, interaction, button):
        index = int(button.label[1:]) - 1  # Extract index from label
        await interaction.response.send_message("Upscaling...")
        upscaled_image = await upscale_image(self.images[index], self.prompt, self.negative_prompt)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        upscaled_image_path = f"./out/upscaledImage_{timestamp}.png"
        upscaled_image.save(upscaled_image_path)
        final_message = f"{interaction.user.mention} aqui está sua imagem em upscale."
        await interaction.channel.send(content=final_message, file=discord.File(fp=upscaled_image_path, filename='upscaled_image.png'))

    @discord.ui.button(label="Re-roll", style=discord.ButtonStyle.green, emoji="🎲", row=0)
    async def reroll_image(self, interaction, btn):
        await interaction.response.send_message(f"{interaction.user.mention} me pediu pare re-criar \"{self.prompt}\", vamos lá...")
        btn.disabled = True
        await interaction.message.edit(view=self)
        # Generate a new image with the same prompt
        images = await generate_images(self.prompt,self.negative_prompt)

        # Construct the final message with user mention
        final_message = f"{interaction.user.mention} me pediu para criar \"{self.prompt}\", aqui o que fiz."
        await interaction.channel.send(content=final_message, file=discord.File(fp=create_collage(images), filename='collage.png'), view = Buttons(self.prompt,self.negative_prompt,images))

@tree.command(name="gerar", description="Gera uma imagem baseada na sua descriçã")
@app_commands.describe(prompt='Prompt para o que você quer gerar')
@app_commands.describe(negative_prompt='Prompt que você quer tentar evitar que a ia gere')
async def slash_command(interaction: discord.Interaction, prompt: str, negative_prompt: str = None):
    # Send an initial message
    await interaction.response.send_message(f"{interaction.user.mention} me pediu para criar \"{prompt}\", isso deve ser rápido...")

    # Generate the image and get progress updates
    images = await generate_images(prompt,negative_prompt)

    # Construct the final message with user mention
    final_message = f"{interaction.user.mention} me pediu para criar \"{prompt}\", aqui o que fiz."
    await interaction.channel.send(content=final_message, file=discord.File(fp=create_collage(images), filename='collage.png'), view=Buttons(prompt,negative_prompt,images))

# run the bot
client.run(TOKEN)
