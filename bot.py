import discord
import discord.ext
from discord import app_commands
import configparser
import os
from PIL import Image
from datetime import datetime
from math import ceil, sqrt

# --- CARREGAMENTO DE CONFIGURAÇÃO ---
def load_config():
    config = configparser.ConfigParser()
    config.read('config.properties', encoding='utf-8') # Encoding utf-8 é importante
    return config

config = load_config()

async def apagar_msg_carregando(interaction: discord.Interaction):
    """Apaga a mensagem de status (Gerando...) sem gerar erro se já sumiu."""
    try:
        await interaction.delete_original_response()
    except:
        pass

# Lendo Token e Source
TOKEN = config['BOT']['TOKEN']
IMAGE_SOURCE = config['BOT']['SDXL_SOURCE']

# --- LENDO CHECKPOINTS DO CONFIG ---
checkpoint_str = config['CHECKPOINTS']['FILES']
default_ckpt_config = config['CHECKPOINTS']['DEFAULT']

# Transforma a string de vírgulas em uma lista, limpando espaços
checkpoint_files = [ckpt.strip() for ckpt in checkpoint_str.split(',') if ckpt.strip()]

# Cria as opções dinamicamente para o Discord
# O "name" será o arquivo limpo (sem pasta e extensão) para ficar bonito no menu
CHECKPOINT_CHOICES = []
for ckpt in checkpoint_files[:25]: # Discord limita a 25 opções
    # Ex: 'anime/nova.safetensors' vira 'nova'
    display_name = os.path.basename(ckpt).replace('.safetensors', '')
    CHECKPOINT_CHOICES.append(app_commands.Choice(name=display_name, value=ckpt))

# --- CONFIGURAÇÕES RECOMENDADAS (Mantive no código pois é lógica complexa) ---
# Se quiser, você pode mover isso para um JSON separado no futuro
MODEL_DEFAULTS = {
    "anime/novaAnimeXL_ilV140.safetensors": {"steps": 25, "cfg": 6.0, "sampler": "euler_ancestral", "scheduler": "normal"},
    "anime/animayhemPaleRider_v2TrueGrit.safetensors": {"steps": 24, "cfg": 3.0, "sampler": "euler_ancestral", "scheduler": "normal"},
    "anime/hassakuXLIllustrious_v32.safetensors": {"steps": 20, "cfg": 6.0, "sampler": "euler_ancestral", "scheduler": "normal"},
    "anime/aniverse_v50.safetensors": {"steps": 30, "cfg": 6.0, "sampler": "dpmpp_2m", "scheduler": "karras"},
    "anime/counterfeitV30_v30.safetensors": {"steps": 25, "cfg": 10.0, "sampler": "dpmpp_2m", "scheduler": "karras"},
    "anime/obsidianAnise_obsidianAniseV10.safetensors": {"steps": 30, "cfg": 4.0, "sampler": "euler_ancestral", "scheduler": "karras"},
    "anime/oneObsession_v18.safetensors": {"steps": 22, "cfg": 5.0, "sampler": "euler_ancestral", "scheduler": "normal"},
    "anime/waiIllustriousSDXL_v150.safetensors": {"steps": 30, "cfg": 7.0, "sampler": "euler_ancestral", "scheduler": "normal"},
    "anime/ramthrustsNSFWPINK_alchemyMix176.safetensors": {"steps": 22, "cfg": 5, "sampler": "euler", "scheduler": "beta"},
    "Real/cyberrealisticPony_v141.safetensors": {"steps": 30, "cfg": 4.0, "sampler": "dpmpp_2m_sde", "scheduler": "karras"},
    "Real/ponyRealism_V23ULTRA.safetensors": {"steps": 30, "cfg": 6.0, "sampler": "dpmpp_2m_sde", "scheduler": "karras"},
    "Real/juggernautXL_ragnarokBy.safetensors":{"steps": 30, "cfg": 5, "sampler": "dpmpp_2m_sde", "scheduler": "karras"},
    "Real/DreamShaper_8_pruned.safetensors":{"steps": 30, "cfg": 7, "sampler": "dpmpp_2m", "scheduler": "karras"},
}

GLOBAL_FALLBACK = {"steps": 25, "cfg": 6.0, "sampler": "euler_ancestral", "scheduler": "normal"}

# Opções fixas de Sampler/Scheduler
SAMPLER_CHOICES = [
    app_commands.Choice(name="DPM++ 2M", value="dpmpp_2m"),
    app_commands.Choice(name="DPM++ 2M SDE", value="dpmpp_2m_sde"),
    app_commands.Choice(name="Euler Ancestral", value="euler_ancestral"),
    app_commands.Choice(name="Euler", value="euler"),
    app_commands.Choice(name="DDIM", value="ddim"),
]

SCHEDULER_CHOICES = [
    app_commands.Choice(name="Karras", value="karras"),
    app_commands.Choice(name="Normal", value="normal"),
    app_commands.Choice(name="Beta", value="beta"),
    app_commands.Choice(name="Exponential", value="exponential"),
    app_commands.Choice(name="Simple", value="simple"),
]

# --- FUNÇÕES AUXILIARES ---

def create_collage(images):
    if not images or len(images) == 0:
        return None

    num_images = len(images)
    num_cols = ceil(sqrt(num_images))
    num_rows = ceil(num_images / num_cols)
    if num_cols == 0: num_cols = 1
    
    collage_width = max(image.width for image in images) * num_cols
    collage_height = max(image.height for image in images) * num_rows
    collage = Image.new('RGB', (collage_width, collage_height))

    for idx, image in enumerate(images):
        row = idx // num_cols
        col = idx % num_cols
        x_offset = col * image.width
        y_offset = row * image.height
        collage.paste(image, (x_offset, y_offset))

    if not os.path.exists('./out'):
        os.makedirs('./out')

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    collage_path = f"./out/collage_{timestamp}.png"
    collage.save(collage_path)
    return collage_path

def preparar_arquivos_separados(images):
    # Função auxiliar caso precise debuggar arquivos individuais
    arquivos_para_envio = []
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    if not os.path.exists('./out'):
        os.makedirs('./out')
    for idx, image in enumerate(images):
        caminho_imagem = f"./out/img_{timestamp}_{idx}.png"
        image.save(caminho_imagem)
        arquivos_para_envio.append(discord.File(fp=caminho_imagem, filename=f'imagem_{idx}.png'))
    return arquivos_para_envio

# --- SETUP DO BOT ---
intents = discord.Intents.default() 
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

if IMAGE_SOURCE == "LOCAL":
    from imageGen import generate_images, upscale_image, generate_alternatives, generate_images_plus
elif IMAGE_SOURCE == "API":
    from apiImageGen import generate_images, upscale_image, generate_alternatives

@client.event
async def on_ready():
    await tree.sync()
    print(f'Logado como {client.user.name} ({client.user.id})')
    print(f'Carregados {len(CHECKPOINT_CHOICES)} modelos do config.')

# --- VIEW DE BOTÕES ---
class Buttons(discord.ui.View):
    def __init__(self, prompt, negative_prompt, images, ckpt_name, steps, cfg, sampler, scheduler, is_plus=False, *, timeout=None):
        super().__init__(timeout=timeout)
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.images = images
        self.ckpt_name = ckpt_name
        # Guardamos na memória
        self.steps = steps
        self.cfg = cfg
        self.sampler = sampler
        self.scheduler = scheduler
        self.is_plus = is_plus # Sabe se veio do /gerar ou /genplus

        if len(images) > 8:
            images = images[:8]

        # Row 1: Extrair Imagem Única
        for idx, _ in enumerate(images):
            row = 1 + (idx // 5) 
            btn = ImageButton(f"{idx + 1}", "📩", row, self.enviar_imagem_unica)
            self.add_item(btn)

        # Row 2: Variação
        for idx, _ in enumerate(images):
            row = 2 + (idx // 5) 
            btn = ImageButton(f"V{idx + 1}", "♻️", row, self.generate_alternatives_and_send)
            self.add_item(btn)

        # Row 3: Upscale
        for idx, _ in enumerate(images):
            row = 3 + (idx // 5)
            if row > 4: row = 4 
            btn = ImageButton(f"U{idx + 1}", "⬆️", row, self.upscale_and_send)
            self.add_item(btn)

    async def enviar_imagem_unica(self, interaction, button):
        index = int(button.label) - 1 
        await interaction.response.send_message(f"Extraindo imagem {button.label}...", ephemeral=False)
        image = self.images[index]
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        single_image_path = f"./out/single_{timestamp}_{index}.png"
        image.save(single_image_path)
        await interaction.channel.send(content=f"{interaction.user.mention} Imagem **{button.label}** separada:", file=discord.File(fp=single_image_path, filename=f'imagem_{button.label}.png'))

    async def generate_alternatives_and_send(self, interaction, button):
            index = int(button.label[1:]) - 1 
            # Mensagem inicial do Discord. ephemeral=False (já corrigimos para público)
            await interaction.response.send_message(f"♻️ Criando variações...", ephemeral=False)
            
            # --- PREPARAÇÃO DO STATUS BASE E CALLBACK ---
            status_msg = (
                f"{interaction.user.mention} ♻️ Criando variações com **{self.ckpt_name}**...\n"
                f"⚙️ Config: Steps: {self.steps} | CFG: {self.cfg}"
            )
            # Edita a mensagem para servir de base para a fila/progresso
            await interaction.edit_original_response(content=status_msg,)

            async def update_discord_status(status_text):
                # Função que será chamada pelo imageGen.py
                await interaction.edit_original_response(content=f"{status_msg}\n> {status_text}...")
            # --------------------------------------------

            images = await generate_alternatives(
                self.images[index], 
                self.prompt, 
                self.negative_prompt, 
                steps=self.steps, 
                cfg=self.cfg, 
                sampler_name=self.sampler, 
                scheduler=self.scheduler, 
                ckpt_name=self.ckpt_name,
                status_callback=update_discord_status # <-- NOVO: Passando o callback
            )
            
            collage_path = create_collage(images)
            await interaction.channel.send(
                content=f"{interaction.user.mention} Variações (Steps: {self.steps} | CFG: {self.cfg}):", 
                file=discord.File(fp=collage_path, filename='collage.png'),
                view=Buttons(self.prompt, self.negative_prompt, images, self.ckpt_name, self.steps, self.cfg, self.sampler, self.scheduler, self.is_plus)
            )
            await apagar_msg_carregando(interaction)


    async def upscale_and_send(self, interaction, button):
        index = int(button.label[1:]) - 1
        await interaction.response.send_message(f"⬆️ Preparando Upscale...", ephemeral=False)
        
        # --- PREPARAÇÃO DO STATUS BASE E CALLBACK ---
        status_msg = f"⬆️ Upscaling com **{self.ckpt_name}** (Workflow Plus)."
        await interaction.edit_original_response(content=status_msg,)

        async def update_discord_status(status_text):
            await interaction.edit_original_response(content=f"{status_msg}\n> {status_text}...")
        # --------------------------------------------

        upscaled_image = await upscale_image(
            self.images[index], 
            self.prompt, 
            self.negative_prompt, 
            ckpt_name=self.ckpt_name,
            status_callback=update_discord_status # <-- NOVO
        )
        
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        upscaled_image_path = f"./out/upscaledImage_{timestamp}.png"
        upscaled_image.save(upscaled_image_path)
        
        await interaction.channel.send(content=f"{interaction.user.mention} Upscale pronto:", file=discord.File(fp=upscaled_image_path, filename='upscaled_image.png'))
        await apagar_msg_carregando(interaction)


    @discord.ui.button(label="Re-roll", style=discord.ButtonStyle.green, emoji="🎲", row=0)
    async def reroll_image(self, interaction, btn):
        await interaction.response.send_message(f"🎲 Preparando Re-roll...", ephemeral=False)
        
        if self.is_plus:
            target_function = generate_images_plus
            mode_text = "PLUS"
        else:
            target_function = generate_images
            mode_text = "Normal"
            
        # --- PREPARAÇÃO DO STATUS BASE E CALLBACK ---
        status_msg = (
            f"🎲 Re-roll {mode_text} com **{self.ckpt_name}**...\n"
            f"⚙️ Config: Steps: {self.steps} | CFG: {self.cfg}"
        )
        await interaction.edit_original_response(content=status_msg,)

        async def update_discord_status(status_text):
            await interaction.edit_original_response(content=f"{status_msg}\n> {status_text}...")
        # --------------------------------------------

        images = await target_function(
            self.prompt, 
            self.negative_prompt, 
            steps=self.steps, 
            cfg=self.cfg, 
            sampler_name=self.sampler, 
            scheduler=self.scheduler, 
            ckpt_name=self.ckpt_name,
            status_callback=update_discord_status # <-- NOVO
        )
        
        collage_path = create_collage(images)
        await interaction.channel.send(
            content=f"{interaction.user.mention} Re-roll {mode_text}:", 
            file=discord.File(fp=collage_path, filename='collage.png'),
            view=Buttons(self.prompt, self.negative_prompt, images, self.ckpt_name, self.steps, self.cfg, self.sampler, self.scheduler, self.is_plus)
        )
        await apagar_msg_carregando(interaction)

class ImageButton(discord.ui.Button):
    def __init__(self, label, emoji, row, callback):
        super().__init__(label=label, style=discord.ButtonStyle.grey, emoji=emoji, row=row)
        self._callback = callback
    async def callback(self, interaction: discord.Interaction):
        await self._callback(interaction, self)

# --- COMANDOS SLASH ---
@tree.command(name="gerar", description="Gera uma imagem. Se não definir opções, usa o recomendado do modelo.")
@app_commands.describe(prompt='O que você quer gerar')
@app_commands.describe(checkpoint='Modelo a ser usado')
@app_commands.describe(negative_prompt='O que evitar')
@app_commands.describe(sampler='Deixe vazio para usar o recomendado do modelo')
@app_commands.describe(scheduler='Deixe vazio para usar o recomendado do modelo')
@app_commands.describe(steps='Deixe vazio para usar o recomendado do modelo')
@app_commands.describe(cfg='Deixe vazio para usar o recomendado do modelo')
@app_commands.choices(sampler=SAMPLER_CHOICES)
@app_commands.choices(scheduler=SCHEDULER_CHOICES)
# AQUI ESTÁ A MÁGICA: Usamos a lista que criamos lá em cima lendo o config
@app_commands.choices(checkpoint=CHECKPOINT_CHOICES)
async def slash_command(
    interaction: discord.Interaction, 
    prompt: str, 
    negative_prompt: str = None,
    steps: int = None,
    cfg: float = None,
    sampler: app_commands.Choice[str] = None,
    scheduler: app_commands.Choice[str] = None,
    checkpoint: app_commands.Choice[str] = None
):
    await interaction.response.send_message(f"{interaction.user.mention} Verificando modelo...", ephemeral=False)

    # 1. Definir Modelo
    if checkpoint:
        final_ckpt_name = checkpoint.value
        display_name = checkpoint.name
    else:
        final_ckpt_name = default_ckpt_config # LIDO DO CONFIG
        display_name = "Padrão (Config)"

    # 2. Carregar recomendações
    recs = MODEL_DEFAULTS.get(final_ckpt_name, {})

    # 3. Prioridade de Parâmetros
    final_steps = steps if steps is not None else recs.get("steps", GLOBAL_FALLBACK["steps"])
    final_cfg = cfg if cfg is not None else recs.get("cfg", GLOBAL_FALLBACK["cfg"])
    
    if sampler:
        final_sampler = sampler.value
    else:
        final_sampler = recs.get("sampler", GLOBAL_FALLBACK["sampler"])

    if scheduler:
        final_scheduler = scheduler.value
    else:
        final_scheduler = recs.get("scheduler", GLOBAL_FALLBACK["scheduler"])

    # --- NOVO BLOCO DE FEEDBACK ---
    # Monta uma mensagem de status mostrando o que foi decidido
    status_msg = (
        f"{interaction.user.mention} :frame_photo: Gerando usando **{display_name}**, deve ser rápidinho...\n"
        f"⚙️ **Config:** Steps: {final_steps} | CFG: {final_cfg} | Sampler: {final_sampler} | Scheduler: {final_scheduler}"
    )
    
    # Atualiza a mensagem "Verificando modelo..." para o status de geração
    await interaction.edit_original_response(content=status_msg,)
    # ------------------------------
    async def update_discord_status(status_text):
        # Edita a mensagem adicionando o status atual no final
        try:
            await interaction.edit_original_response(content=f"{status_msg}\n> {status_text}...")
        except:
            pass # Ignora erros de rate limit do Discord se for muito rápido

    try:
        images = await generate_images(
            prompt, 
            negative_prompt, 
            steps=final_steps, 
            cfg=final_cfg, 
            sampler_name=final_sampler, 
            scheduler=final_scheduler, 
            ckpt_name=final_ckpt_name,
            status_callback=update_discord_status
        )
    except Exception as e:
        await interaction.channel.send(f"Erro crítico no ComfyUI: {e}", ephemeral=True)
        return

    if not images:
        await interaction.channel.send("O ComfyUI não retornou imagens.", ephemeral=True)
        return

    infos = f"**Model:** {display_name}\n**Params:** Steps: {final_steps} | CFG: {final_cfg} | {final_sampler} / {final_scheduler}"
    collage_path = create_collage(images)

    await interaction.edit_original_response(
        content=f"{interaction.user.mention} {infos}\n> **Prompt:** {prompt} **Negative Prompt:** {negative_prompt}", 
        attachments=[discord.File(fp=collage_path, filename='collage.png')], 
        view=Buttons(prompt, negative_prompt, images, final_ckpt_name, final_steps, final_cfg, final_sampler, final_scheduler, is_plus=False)
    )

# --- COMANDO GERAR PLUS ---
@tree.command(name="genplus", description="Gera imagem com Workflow PLUS (Mais detalhes/qualidade). ✨")
@app_commands.describe(prompt='O que você quer gerar')
@app_commands.describe(checkpoint='Modelo a ser usado')
@app_commands.describe(negative_prompt='O que evitar')
@app_commands.describe(sampler='Deixe vazio para usar o recomendado do modelo')
@app_commands.describe(scheduler='Deixe vazio para usar o recomendado do modelo')
@app_commands.describe(steps='Deixe vazio para usar o recomendado do modelo')
@app_commands.describe(cfg='Deixe vazio para usar o recomendado do modelo')
@app_commands.choices(sampler=SAMPLER_CHOICES)
@app_commands.choices(scheduler=SCHEDULER_CHOICES)
# AQUI ESTÁ A MÁGICA: Usamos a lista que criamos lá em cima lendo o config
@app_commands.choices(checkpoint=CHECKPOINT_CHOICES)
async def gerarplus_command( 
    interaction: discord.Interaction, 
    prompt: str, 
    negative_prompt: str = None,
    steps: int = None,
    cfg: float = None,
    sampler: app_commands.Choice[str] = None,
    scheduler: app_commands.Choice[str] = None,
    checkpoint: app_commands.Choice[str] = None
):
    await interaction.response.send_message(f"{interaction.user.mention} Verificando modelo...", ephemeral=False)

    # 1. Definir Modelo
    if checkpoint:
        final_ckpt_name = checkpoint.value
        display_name = checkpoint.name
    else:
        final_ckpt_name = default_ckpt_config # LIDO DO CONFIG
        display_name = "Padrão (Config)"

    # 2. Carregar recomendações
    recs = MODEL_DEFAULTS.get(final_ckpt_name, {})

    # 3. Prioridade de Parâmetros
    final_steps = steps if steps is not None else recs.get("steps", GLOBAL_FALLBACK["steps"])
    final_cfg = cfg if cfg is not None else recs.get("cfg", GLOBAL_FALLBACK["cfg"])
    
    if sampler:
        final_sampler = sampler.value
    else:
        final_sampler = recs.get("sampler", GLOBAL_FALLBACK["sampler"])

    if scheduler:
        final_scheduler = scheduler.value
    else:
        final_scheduler = recs.get("scheduler", GLOBAL_FALLBACK["scheduler"])

    # --- NOVO BLOCO DE FEEDBACK ---
    # Monta uma mensagem de status mostrando o que foi decidido
    status_msg = (
        f"{interaction.user.mention} :frame_photo: Gerando usando **{display_name}** e detalhadores...\n"
        f"⚙️ **Config:** Steps: {final_steps} | CFG: {final_cfg} | Sampler: {final_sampler} | Scheduler: {final_scheduler}"
    )
    
    # Atualiza a mensagem "Verificando modelo..." para o status de geração
    await interaction.edit_original_response(content=status_msg,)
    
    async def update_discord_status(status_text):
        try:
            await interaction.edit_original_response(content=f"{status_msg}\n> {status_text}...")
        except:
            pass
    # ------------------------------

    try:
        images = await generate_images_plus(
            prompt, 
            negative_prompt, 
            steps=final_steps, 
            cfg=final_cfg, 
            sampler_name=final_sampler, 
            scheduler=final_scheduler, 
            ckpt_name=final_ckpt_name,
            status_callback=update_discord_status
        )
    except Exception as e:
        await interaction.channel.send(f"Erro crítico no ComfyUI: {e}", ephemeral=True)
        return

    if not images:
        await interaction.channel.send("O ComfyUI não retornou imagens.", ephemeral=True)
        return

    infos = f"**Model:** {display_name}\n**Params:** Steps: {final_steps} | CFG: {final_cfg} | {final_sampler} / {final_scheduler}"
    collage_path = create_collage(images)

    await interaction.edit_original_response(
        content=f"{interaction.user.mention} {infos}\n> **Prompt:** {prompt} **Negative Prompt:** {negative_prompt}", 
        attachments=[discord.File(fp=collage_path, filename='collage.png')], 
        view=Buttons(prompt, negative_prompt, images, final_ckpt_name, final_steps, final_cfg, final_sampler, final_scheduler, is_plus=False)
    )

# --- COMANDO HELP (BÁSICO) ---
@tree.command(name="help", description="Aprenda o básico para gerar imagens comigo! 🎨")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="✨ Como usar a Vivimage ✨",
        description="Aqui está tudo que você precisa saber para começar a criar obras de arte!",
        color=discord.Color.magenta()
    )
    
    # Prioridade pedida: Prompt e Checkpoint
    embed.add_field(
        name="📝 1. Prompt (Obrigatório)",
        value="É a descrição do que você quer ver. Quanto mais detalhado, melhor!\n*Ex: `masterpiece, high quality, a ciberpunk girl, neon lights, rain`*",
        inline=False
    )
    
    embed.add_field(
        name="🎨 2. Checkpoint (O Estilo)",
        value="Define o traço da imagem (Anime, Realista, 3D, etc). Se você não escolher um, eu uso meu **Config Padrão** automaticamente. Meu padrão é o https://civitai.com/models/376130/nova-anime-xl. Para saber quais checkpoints temos, use /checkpoints",
        inline=False
    )

    embed.add_field(
        name="🚫 3. Negative Prompt (Opcional)",
        value="O que você **NÃO** quer na imagem.\n*Ex: `ugly, bad quality, worst quality, deformed, bad hands, black and white, nsfw`*",
        inline=False
    )
    
    embed.add_field(
        name=":writing_hand: Example Full Prompt",
        value="/gerar prompt:embedding:lazypos, cinematic composition, masterpiece, best quality, hyper detailed, cinematic composition, 1girl, long hair, ginger hair,  pajamas, heart eyes eyeliner, silver sequined dress, minidress, plunging neckline, dark blue eyebrows, black lipstick, walking, cyberpunk city, streets, negative_prompt:embedding:lazyhand,  embedding:lazyneg, bad quality, worst quality, worst detail, sketch, bad hands, bad fingers, multiple fingers, bad anatomy, deformed, artist name, watermark, signature, patreon, twitter username, shiny clothes, shiny skin, checkpoint:oneObsession_v18"
    )
    
    embed.set_footer(text="Quer mexer nos detalhes técnicos ou me conhecer mais? Use /help_advanced ou /info")
    
    await interaction.response.send_message(embed=embed)

# --- COMANDO HELP (AVANÇADO) ---
@tree.command(name="help_advanced", description="Entenda os parâmetros técnicos (Steps, CFG, Samplers). 🤓")
async def help_advanced_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔧 Configurações Avançadas",
        description="Seus controles finos para alterar como a IA 'pensa'.",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="👣 Steps (Passos)",
        value="Quantas vezes a IA refina a imagem. \n• **Mais Steps:** Mais detalhe (mas demora mais). \n• **Menos Steps:** Mais rápido (pode ficar borrado). \n*Recomendado: 20 a 30.*",
        inline=False
    )
    
    embed.add_field(
        name="⚖️ CFG Scale (Guidance)",
        value="O quanto a IA deve obedecer seu prompt fielmente.\n• **Baixo (3-5):** IA mais criativa/livre.\n• **Alto (7-12):** Segue o texto à risca (pode saturar a imagem).",
        inline=False
    )
    
    embed.add_field(
        name="🧮 Sampler & Scheduler",
        value="São os algoritmos matemáticos que removem o ruído.\n• **Euler A / DPM++ SDE:** Mais criativos e variados.\n• **DPM++ 2M / Karras:** Mais rápidos e nítidos.\n*Dica: Cada modelo prefere um diferente!*",
        inline=False
    )
    
    embed.add_field(
        name=":writing_hand: TIPS",
        value="• O upscale sempre vai passar por detalhadores, então genplus deve ser usado mais quando não quer usar upscale depois.\n• Se já tiver um bom prompt preparado, use **/genplus**, esse gerador demora mais, mas passa por detalhadores que melhoram partes da imagem. "
    )

    await interaction.response.send_message(embed=embed)

# --- COMANDO INFO ---
@tree.command(name="info", description="Quem sou eu? Créditos e informações do sistema. ℹ️")
async def info_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Oiê! Eu sou a Vivimage! :heart_eyes:",
        description="Sou uma bot excitada para transformar suas ideias em imagens incríveis usando Inteligência Artificial Local!",
        color=discord.Color.gold()
    )
    
    if client.user.avatar:
        embed.set_thumbnail(url=client.user.avatar.url)

    embed.add_field(
        name="🤖 Sobre Mim",
        value="Eu rodo em uma infraestrutura **Ryzen 9+ 32gb RAM + RX 9070 XT**, usando **ComfyUI** para geração rápida e otimizada.",
        inline=False
    )

    embed.add_field(
        name="🛠️ Créditos de Desenvolvimento",
        value=(
            "• **Developer:** Usnad\n"
            "• **AI Partner:** Gemini (Google)\n"
            "• **Base Code:** Fork do projeto de `aaronfisher-code`"
        ),
        inline=False
    )
    
    embed.set_footer(text=f"Versão 2.0 | Vivimage System | Ping: {round(client.latency * 1000)}ms")

    await interaction.response.send_message(embed=embed)

# --- COMANDO CHECKPOINTS ---
@tree.command(name="checkpoints", description="Lista todos os modelos instalados e seus links. 📚")
async def checkpoints_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 Biblioteca de Checkpoints",
        description="Abaixo estão todos os modelos disponíveis no sistema.",
        color=discord.Color.purple()
    )

    # 1. O PADRÃO (Destaque)
    embed.add_field(
        name="🌟 PADRÃO: DreamShaper 8",
        value="[Link Civitai](https://civitai.com/models/4384/dreamshaper) | *O modelo 'faz-tudo'. Ótimo para começar.*",
        inline=False
    )

    # 2. Anime Parte 1 (A-H)
    anime_list_1 = (
        "**• Animayhem Pale Rider**\n"
        "[Link Civitai](https://civitai.com/models/1984400/animayhem-pale-rider) | *Estilo 'Gritty', alto contraste e detalhes.*\n\n"

        "**• Aniverse v5.0**\n"
        "[Link Civitai](https://civitai.com/models/107842/aniverse) | *Anime moderno vibrante, estilo TV/Série.*\n\n"
        
        "**• Counterfeit V3.0**\n"
        "[Link Civitai](https://civitai.com/models/4468/counterfeit-v30) | *Estilo 'pintura digital' suave e artístico.*\n\n"
        
        "**• Hassaku XL Illustrious**\n"
        "[Link Civitai](https://civitai.com/models/140272/hassaku-xl-illustrious) | *Traço limpo, cores chapadas (Flat Color).*\n\n"
        
        "**• Nova Anime XL v40**\n"
        "[Link Civitai](https://civitai.com/models/376130/nova-anime-xl) | *Excelente qualidade geral para SDXL Anime.*"
    )
    embed.add_field(name="🎨 Anime & Ilustração (Parte 1)", value=anime_list_1, inline=False)

    # 3. Anime Parte 2 (O-W)
    anime_list_2 = (
        "**• Obsidian Anise**\n"
        "[Link Civitai](https://civitai.com/models/2143097/obsidian-anise) | *Anime semi-realista (2.5D) com boa luz.*\n\n"
        
        "**• One Obsession**\n"
        "[Link Civitai](https://civitai.com/models/1318945/one-obsession) | *Traço nítido e altamente detalhado.*\n\n"
        
        "**• Wai Illustrious SDXL**\n"
        "[Link Civitai](https://civitai.com/models/827184/wai-illustrious-sdxl) | *Baseado no Illustrious, traço consistente.*\n\n"
        
        "**• Ramthrust's Alchemy Mix**\n"
        "[Link Civitai](https://civitai.com/models/1465491/ramthrusts-nsfw-pink-alchemy-mix) | *Mix específico (foco em NSFW/Pink).*"
    )
    embed.add_field(name="🎨 Anime & Ilustração (Parte 2)", value=anime_list_2, inline=False)

    # 4. Pony, Realismo & Especiais
    special_list = (
        "**• CyberRealistic Pony**\n"
        "[Link Civitai](https://civitai.com/models/443821?modelVersionId=2255476) | *Flexibilidade do Pony com texturas reais.*\n\n"
        
        "**• Pony Realism**\n"
        "[Link Civitai](https://civitai.com/models/372465?modelVersionId=1920896) | *Mistura realismo fotográfico na base Pony.*\n\n"
        
        "**• Juggernaut XL**\n"
        "[Link Civitai](https://civitai.com/models/133005?modelVersionId=1759168) | *O rei do fotorealismo e cinematic.*"
    )
    embed.add_field(name="🦄 Pony / Realismo / Especiais", value=special_list, inline=False)
    
    await interaction.response.send_message(embed=embed)
# run the bot
client.run(TOKEN)