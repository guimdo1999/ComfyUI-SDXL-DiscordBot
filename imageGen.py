import websockets
import uuid
import json
import random
import urllib.request
import urllib.parse
from PIL import Image
from io import BytesIO
import configparser
import os
import tempfile
import requests

# Read the configuration
config = configparser.ConfigParser()
config.read('config.properties', encoding='utf-8')
server_address = config['LOCAL']['SERVER_ADDRESS']
text2img_config = config['LOCAL_TEXT2IMG']['CONFIG']
text2imgplus_config = config['LOCAL_TEXT2IMG_PLUS']['CONFIG']
img2img_config = config['LOCAL_IMG2IMG']['CONFIG']
upscale_config = config['LOCAL_UPSCALE']['CONFIG']

callback_time = 3600 # Define o tempo para realizar ações em botões em segundos.

# Seta modelos de upscale
upscalePeople="4x_NickelbackFS_72000_G.pth"
upscaleAnime="2xNomosUni_esrgan_multijpg.pth"

NODE_TRANSLATION = {
    # Checkpoint
    "Checkpoint Loader (Simple)": "📚 Carregando Modelo",
    
    # Loras (Você usa o do rgthree)
    "Power Lora Loader (rgthree)": "💊 Aplicando Loras",
    
    # Prompts
    "CLIPTextEncode": "🧠 Lendo Prompt",
    "CLIPSetLastLayer": "🎚️ Ajustando Clip Skip",
    
    # Preparação
    "EmptyLatentImage": "📐 Preparando Tela",
    
    # Geração (Você usa KSamplerAdvanced)
    "KSamplerAdvanced": "🎨 Desenhando (Sampling)",
    "KSampler": "🎨 Desenhando",
    
    # Decodificação (Você usa o Tiled)
    "VAEDecodeTiled": "🖼️ Decodificando (Tiled)",
    "VAEDecode": "🖼️ Decodificando",
    
    # Detalhadores (Não estão nesse JSON, mas deixe aqui para o GerarPlus)
    "FaceDetailer": "👀 Melhorando 'Rostos'",
    "FaceDetailerPipe": "👀 Melhorando 'Rostos'",
    "ImageUpscaleWithModel": "⬆️ Fazendo Upscale",
    
    # Salvamento (Você usa o Image Save customizado)
    "Image Save": "💾 Salvando Imagem",
    "SaveImage": "💾 Salvando Imagem",
    
    # Extras
    "CR Seed": "🌱 Semeando o Caos"
}

def queue_prompt(prompt, client_id):
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req =  urllib.request.Request("http://{}/prompt".format(server_address), data=data)
    return json.loads(urllib.request.urlopen(req).read())

def get_queue_info():
    try:
        with urllib.request.urlopen(f"http://{server_address}/queue") as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"Erro ao ler fila: {e}")
        return {"queue_running": [], "queue_pending": []}

def get_image(filename, subfolder, folder_type):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen("http://{}/view?{}".format(server_address, url_values)) as response:
        return response.read()

def get_history(prompt_id):
    with urllib.request.urlopen("http://{}/history/{}".format(server_address, prompt_id)) as response:
        return json.loads(response.read())
    
def upload_image(filepath, subfolder=None, folder_type=None, overwrite=False):
    url = f"http://{server_address}/upload/image"
    files = {'image': open(filepath, 'rb')}
    data = {
        'overwrite': str(overwrite).lower()
    }
    if subfolder:
        data['subfolder'] = subfolder
    if folder_type:
        data['type'] = folder_type
    response = requests.post(url, files=files, data=data)
    return response.json()

# --- FUNÇÃO AUXILIAR INTELIGENTE PARA SETAR VALORES ---
def set_node_values(workflow, nodes_str, field_key, value, is_string_number=False):
    """
    Lê a string de nós do config (ex: "89, 90"), itera sobre eles e define o valor.
    Tenta ser inteligente sobre o nome do campo se field_key for genérico.
    """
    if not nodes_str or nodes_str.strip() == "":
        return

    node_ids = [n.strip() for n in nodes_str.split(',') if n.strip()]
    
    for node_id in node_ids:
        if node_id in workflow:
            inputs = workflow[node_id]['inputs']
            
            # Tratamento especial para CFG que as vezes é String no ComfyUI
            final_value = str(value) if is_string_number else value

            # Se o campo solicitado existe, usa ele
            if field_key in inputs:
                inputs[field_key] = final_value
            # Se não, tenta adivinhar campos comuns para Primitives
            elif 'value' in inputs:
                inputs['value'] = final_value
            elif 'Number' in inputs: # Caso específico do nó Float to String
                inputs['Number'] = str(value)
            elif 'text' in inputs and isinstance(value, str):
                inputs['text'] = value
            elif 'string_b' in inputs and isinstance(value, str): # Concatenate
                 inputs['string_b'] = value

class ImageGenerator:
    def __init__(self):
        self.client_id = str(uuid.uuid4())
        self.uri = f"ws://{server_address}/ws?clientId={self.client_id}"
        self.ws = None

    async def connect(self):
        self.ws = await websockets.connect(self.uri)

    # ALTERAÇÃO AQUI: Adicionado status_callback
    async def get_images(self, workflow, status_callback=None):
        if not self.ws:
            await self.connect()
            
        try:
            # 1. Envia o prompt
            prompt_response = queue_prompt(workflow, self.client_id)
            prompt_id = prompt_response['prompt_id']
            
            # --- CÁLCULO DA FILA (NOVO) ---
            # Verifica imediatamente onde fomos parar
            if status_callback and callable(status_callback):
                queue_data = get_queue_info()
                running = queue_data.get('queue_running', [])
                pending = queue_data.get('queue_pending', [])
                
                position = 0
                found = False

                # Se já tem gente rodando, a fila começa depois deles
                if len(running) > 0:
                    # Verifica se SOU EU rodando agora
                    for task in running:
                        if task[1] == prompt_id:
                            await status_callback("🔨 Já iniciou o processamento...")
                            found = True
                            break
                    if not found:
                        position += len(running)

                # Se não estou rodando, procuro minha posição na espera
                if not found:
                    for i, task in enumerate(pending):
                        if task[1] == prompt_id:
                            # Minha posição é: quem tá rodando + quantos estão na minha frente + eu
                            my_real_pos = position + i + 1
                            await status_callback(f"⏳ Na fila: Posição {my_real_pos}")
                            found = True
                            break
            # -----------------------------

        except Exception as e:
            print(f"Erro ao enviar prompt para o ComfyUI: {e}")
            return []

        output_images = []
            
        async for out in self.ws:
            try:
                message = json.loads(out)

                    
                if message['type'] == 'executing':
                    data = message['data']
                    if data['node'] is None and data['prompt_id'] == prompt_id:
                        break 

                    # Adicionado 'callable(status_callback)'
                    if status_callback and callable(status_callback) and data['node'] in workflow:
                        node_id = data['node']
                        node_class = workflow[node_id].get('class_type', 'Unknown')
                        readable_status = NODE_TRANSLATION.get(node_class, f"⚙️ Processando: {node_class}")
                        
                        try:
                            await status_callback(readable_status)
                        except Exception as e:
                            print(f"Erro ao atualizar status: {e}")

            except ValueError as e:
                print("Incompatible response from ComfyUI")
                
        history = get_history(prompt_id)[prompt_id]

        for node_id in history['outputs']:
            node_output = history['outputs'][node_id]
            if 'images' in node_output:
                for image in node_output['images']:
                    image_data = get_image(image['filename'], image['subfolder'], image['type'])
                    if 'final_output' in image['filename'] or 'upscaled' in image['filename'] or 'output' in image['filename']:
                        pil_image = Image.open(BytesIO(image_data))
                        output_images.append(pil_image)
                    elif len(output_images) == 0:
                        pil_image = Image.open(BytesIO(image_data))
                        output_images.append(pil_image)

        return output_images

    async def close(self):
        if self.ws:
            await self.ws.close()

# --- FUNÇÃO Txt2Img ---
async def generate_images(prompt: str, negative_prompt: str, steps=25, cfg=7.0, sampler_name="dpmpp_2m", scheduler="karras", ckpt_name=None, status_callback=callback_time):
    with open(text2img_config, 'r', encoding='utf-8') as file:
      workflow = json.load(file)
      
    generator = ImageGenerator()
    await generator.connect()

    # Leitura dos IDs do Config
    section = 'LOCAL_TEXT2IMG'
    
    # 1. Prompts
    # Tenta usar keys específicas se existirem, senão usa PROMPT_NODES
    set_node_values(workflow, config.get(section, 'PROMPT_NODES', fallback=''), 'text', prompt) # Tenta 'text' ou 'string_b' automaticamente
    clip_skip_nodes = config.get(section, 'CLIP_SKIP_NODES', fallback='')
    
   # CLIP SKIP 
    if ckpt_name == "anime/ramthrustsNSFWPINK_alchemyMix176.safetensors":
        # Força stop_at_last_layers = -1 (Clip Skip 1)
        set_node_values(workflow, clip_skip_nodes, 'stop_at_last_layers', -1)
    else: 
        set_node_values(workflow, clip_skip_nodes, 'stop_at_last_layers', -2)
        
    neg_nodes = config.get(section, 'NEG_PROMPT_NODES', fallback='')
    if negative_prompt:
        set_node_values(workflow, neg_nodes, 'text', negative_prompt)
    else:
        # Se não tiver negativo, limpa o campo (importante para string_b não ficar com lixo)
        set_node_values(workflow, neg_nodes, 'text', "")

    # 2. Steps
    set_node_values(workflow, config.get(section, 'STEPS_NODES', fallback=''), 'value', steps)

    # 3. CFG (flag is_string_number=True para forçar conversão para string se necessário)
    set_node_values(workflow, config.get(section, 'CFG_NODES', fallback=''), 'Number', cfg, is_string_number=True)

    # 4. Checkpoint
    if ckpt_name:
        set_node_values(workflow, config.get(section, 'CHECKPOINT_NODES', fallback=''), 'ckpt_name', ckpt_name)

    # 5. Sampler e Scheduler
    # KSampler geralmente tem inputs fixos 'sampler_name' e 'scheduler'
    sampler_nodes = config.get(section, 'SAMPLER_NODES', fallback='').split(',')
    for node in sampler_nodes:
        if node.strip() in workflow:
            workflow[node.strip()]['inputs']['sampler_name'] = sampler_name
            workflow[node.strip()]['inputs']['scheduler'] = scheduler

    # 6. Seed
    seed_nodes = config.get(section, 'RAND_SEED_NODES', fallback='')
    set_node_values(workflow, seed_nodes, 'seed', random.randint(1, 999999999999999))

    images = await generator.get_images(workflow, status_callback=status_callback)
    await generator.close()
    return images

# --- FUNÇÃO Txt2Img PLUS---
async def generate_images_plus(prompt: str, negative_prompt: str, steps=25, cfg=7.0, sampler_name="dpmpp_2m", scheduler="karras", ckpt_name=None, status_callback=callback_time):
    # CORREÇÃO 1: Usa a variável do config PLUS, não a normal
    with open(text2imgplus_config, 'r', encoding='utf-8') as file:
      workflow = json.load(file)
      
    generator = ImageGenerator()
    await generator.connect()

    # CORREÇÃO 2: Aponta para a seção nova do config.properties para ler os IDs certos
    section = 'LOCAL_TEXT2IMG_PLUS'
    
    # 1. Prompts
    set_node_values(workflow, config.get(section, 'PROMPT_NODES', fallback=''), 'text', prompt) 
    clip_skip_nodes = config.get(section, 'CLIP_SKIP_NODES', fallback='')
    
   # CLIP SKIP 
    if ckpt_name == "anime/ramthrustsNSFWPINK_alchemyMix176.safetensors":
        set_node_values(workflow, clip_skip_nodes, 'stop_at_last_layers', -1)
    else: 
        set_node_values(workflow, clip_skip_nodes, 'stop_at_last_layers', -2)
        
    neg_nodes = config.get(section, 'NEG_PROMPT_NODES', fallback='')
    if negative_prompt:
        set_node_values(workflow, neg_nodes, 'text', negative_prompt)
    else:
        set_node_values(workflow, neg_nodes, 'text', "")

    # 2. Steps, CFG, Checkpoint, Seed
    # Note que agora o 'config.get(section...)' vai ler da seção PLUS automaticamente
    set_node_values(workflow, config.get(section, 'STEPS_NODES', fallback=''), 'value', steps)
    set_node_values(workflow, config.get(section, 'CFG_NODES', fallback=''), 'Number', cfg, is_string_number=True)

    if ckpt_name:
        set_node_values(workflow, config.get(section, 'CHECKPOINT_NODES', fallback=''), 'ckpt_name', ckpt_name)

    # 5. Sampler e Scheduler
    sampler_nodes = config.get(section, 'SAMPLER_NODES', fallback='').split(',')
    for node in sampler_nodes:
        if node.strip() in workflow:
            workflow[node.strip()]['inputs']['sampler_name'] = sampler_name
            workflow[node.strip()]['inputs']['scheduler'] = scheduler

    # 6. Seed
    seed_nodes = config.get(section, 'RAND_SEED_NODES', fallback='')
    set_node_values(workflow, seed_nodes, 'seed', random.randint(1, 999999999999999))

    images = await generator.get_images(workflow, status_callback=status_callback)
    await generator.close()

    return images

# --- FUNÇÃO Img2Img ---
async def generate_alternatives(image: Image.Image, prompt: str, negative_prompt: str, steps=None, cfg=None, sampler_name=None, scheduler=None, ckpt_name=None, status_callback=callback_time):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
      image.save(temp_file, format="PNG")
      temp_filepath = temp_file.name

    response_data = upload_image(temp_filepath)
    filename = response_data['name']
    
    with open(img2img_config, 'r', encoding='utf-8') as file:
      workflow = json.load(file)
      
    generator = ImageGenerator()
    await generator.connect()
    
    section = 'LOCAL_IMG2IMG'

    # 1. Inputs Básicos
    set_node_values(workflow, config.get(section, 'PROMPT_NODES', fallback=''), 'text', prompt)
    set_node_values(workflow, config.get(section, 'NEG_PROMPT_NODES', fallback=''), 'text', negative_prompt)
    set_node_values(workflow, config.get(section, 'RAND_SEED_NODES', fallback=''), 'seed', random.randint(1, 999999999999999))
    set_node_values(workflow, config.get(section, 'FILE_INPUT_NODES', fallback=''), 'image', filename)

    # 2. Checkpoint e Clip Skip
    if ckpt_name:
        set_node_values(workflow, config.get(section, 'CHECKPOINT_NODES', fallback=''), 'ckpt_name', ckpt_name)
        
    clip_skip_nodes = config.get(section, 'CLIP_SKIP_NODES', fallback='')
    if ckpt_name == "anime/ramthrustsNSFWPINK_alchemyMix176.safetensors":
        set_node_values(workflow, clip_skip_nodes, 'stop_at_last_layers', -1)
    else: 
        set_node_values(workflow, clip_skip_nodes, 'stop_at_last_layers', -2)

    # 3. Steps e CFG (VOLTAMOS PARA O MODO PRIMITIVE)
    if steps:
        # Passamos 'value' porque nós primitivos usam esse campo
        set_node_values(workflow, config.get(section, 'STEPS_NODES', fallback=''), 'value', steps)
        
    if cfg:
        # Passamos 'Number' ou 'value'. Sua função set_node_values é inteligente e tenta 'value' se 'Number' falhar.
        # Use 'Number' se for aquele nó "Float" específico, ou 'value' se for Primitive Node.
        # Vou deixar 'Number' com is_string_number=True por segurança, mas sua função trata.
        set_node_values(workflow, config.get(section, 'CFG_NODES', fallback=''), 'Number', cfg, is_string_number=True)
        
    # 4. Sampler e Scheduler (Continua injetando direto no KSampler)
    if sampler_name and scheduler:
        sampler_nodes = config.get(section, 'SAMPLER_NODES', fallback='').split(',')
        for node in sampler_nodes:
            if node.strip() in workflow:
                workflow[node.strip()]['inputs']['sampler_name'] = sampler_name
                workflow[node.strip()]['inputs']['scheduler'] = scheduler

    images = await generator.get_images(workflow)
    await generator.close()

    return images

# --- FUNÇÃO Upscale ---
async def upscale_image(image: Image.Image, prompt: str, negative_prompt: str, ckpt_name=None, status_callback=callback_time):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
      image.save(temp_file, format="PNG")
      temp_filepath = temp_file.name

    response_data = upload_image(temp_filepath)
    filename = response_data['name']
    
    with open(upscale_config, 'r', encoding='utf-8') as file:
      workflow = json.load(file)

    generator = ImageGenerator()
    await generator.connect()

    section = 'LOCAL_UPSCALE'

    # 1. Inputs Básicos
    set_node_values(workflow, config.get(section, 'PROMPT_NODES', fallback=''), 'text', prompt)
    set_node_values(workflow, config.get(section, 'NEG_PROMPT_NODES', fallback=''), 'text', negative_prompt)
    set_node_values(workflow, config.get(section, 'RAND_SEED_NODES', fallback=''), 'seed', random.randint(1, 999999999999999))
    set_node_values(workflow, config.get(section, 'FILE_INPUT_NODES', fallback=''), 'image', filename)

    # 2. Checkpoint Principal
    if ckpt_name:
        set_node_values(workflow, config.get(section, 'CHECKPOINT_NODES', fallback=''), 'ckpt_name', ckpt_name)

    # 1. Inputs Básicos (Prompt, Negativo, Seed, Imagem)
    clip_skip_nodes = config.get(section, 'CLIP_SKIP_NODES', fallback='')
    
    # CLIP SKIP 
    if ckpt_name == "anime/ramthrustsNSFWPINK_alchemyMix176.safetensors":
        # Força stop_at_last_layers = -1 (Clip Skip 1)
        set_node_values(workflow, clip_skip_nodes, 'stop_at_last_layers', -1)
    else: 
        set_node_values(workflow, clip_skip_nodes, 'stop_at_last_layers', -2)
    
    upscaleModel = upscalePeople
    if "anime" in ckpt_name:
         upscaleModel = upscaleAnime

    # 3. Forçar Modelo de Upscale
    # Adicione UPSCALE_MODEL_NODES=[ID] no seu config na seção LOCAL_UPSCALE
    upscale_model_nodes = config.get(section, 'UPSCALE_MODEL_NODES', fallback='')
    if upscale_model_nodes:
        set_node_values(workflow, upscale_model_nodes, 'model_name', upscaleModel)
        
    ancestral_samplers = ["euler_ancestral", "dpmpp_2s_ancestral", "dpmpp_sde", "dpmpp_2m_sde", "dpmpp_3m_sde"]
    ultimate_upscale_node = "6"
    current_sampler = workflow[ultimate_upscale_node]['inputs'].get('sampler_name', 'dpmpp_2m')
    
    if current_sampler in ancestral_samplers:
        # Se for Ancestral, ativa o Band Pass para esconder as linhas
        workflow[ultimate_upscale_node]['inputs']['seam_fix_mode'] = "Band Pass"
        workflow[ultimate_upscale_node]['inputs']['seam_fix_denoise'] = 0.2 # Um leve blur na emenda
        # print(f"DEBUG: Seam Fix ATIVADO para {current_sampler}")
    else:
        # Se for dpmpp_2m ou Euler normal, desliga para ganhar performance e nitidez
        workflow[ultimate_upscale_node]['inputs']['seam_fix_mode'] = "None"
        # print(f"DEBUG: Seam Fix DESLIGADO para {current_sampler}")

    images = await generator.get_images(workflow, status_callback=status_callback)
    await generator.close()

    return images[0]