import argparse
import os
import random

import numpy as np
import torch
import torch.backends.cudnn as cudnn
import os
from tqdm import tqdm
import json

from video_llama.common.config import Config
from video_llama.common.dist_utils import get_rank
from video_llama.common.registry import registry
from video_llama.conversation.conversation_video import Chat, Conversation, default_conversation,SeparatorStyle,conv_llava_llama_2
import decord
decord.bridge.set_bridge('torch')

from video_llama.datasets.builders import *
from video_llama.models import *
from video_llama.processors import *
from video_llama.runners import *
from video_llama.tasks import *

def parse_args():
    parser = argparse.ArgumentParser(description="Demo")
    parser.add_argument("--cfg-path", default='eval_configs/video_llama_eval_withaudio.yaml', help="path to configuration file.")
    parser.add_argument("--gpu-id", type=int, default=0, help="specify the gpu to load the model.")
    parser.add_argument("--model_type", type=str, default='llama_v2', help="The type of LLM")
    parser.add_argument(
        "--options",
        nargs="+",
        help="override some settings in the used config, the key-value pair "
        "in xxx=yyy format will be merged into config file (deprecate), "
        "change to --cfg-options instead.",
    )
    args = parser.parse_args("")
    return args

def setup_seeds(config):
    seed = config.run_cfg.seed + get_rank()

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    cudnn.benchmark = False
    cudnn.deterministic = True
    

print('Initializing Chat')
args = parse_args()
print(args)
cfg = Config(args)

model_config = cfg.model_cfg
model_config.device_8bit = args.gpu_id
model_cls = registry.get_model_class(model_config.arch)
model = model_cls.from_config(model_config).to('cuda:{}'.format(args.gpu_id))
model.eval()
vis_processor_cfg = cfg.datasets_cfg.webvid.vis_processor.train
vis_processor = registry.get_processor_class(vis_processor_cfg.name).from_config(vis_processor_cfg)
chat = Chat(model, vis_processor, device='cuda:{}'.format(args.gpu_id))
print('Initialization Finished')

def gradio_reset(chat_state, img_list):
    if chat_state is not None:
        chat_state.messages = []
    if img_list is not None:
        img_list = []
        
# configs
user_message = "Describe the video briefly."
num_beams = 1
temperature = 1.0

def get_description(file_path):
    chat_state = conv_llava_llama_2.copy()
    chat_state.system =  ""
    img_list = []
    llm_message = chat.upload_video(file_path, chat_state, img_list)
    chat.ask(user_message, chat_state)
    llm_message = chat.answer(conv=chat_state,
                                img_list=img_list,
                                num_beams=num_beams,
                                temperature=temperature,
                                max_new_tokens=300,
                                max_length=2000)[0]
    return llm_message

llm_results = {}
ground_truth = {}

def find_files(root_dir, file_name):
    matching_files = []
    
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file == file_name:
                matching_files.append(os.path.join(root, file))
    
    return matching_files

root_directory = "./data/werewolf/chunk"

data = []

for root, dirs, files in os.walk(root_directory):
    for file in files:
        data.append(os.path.join(root, file))
for i in tqdm(range(len(data))):
    file = data[i]
    try:
        llm_results = get_description(file)
        filename = (file.split(os.sep)[-1]).split('.')[0]
        with open(f"./data/werewolf/results/{filename}", 'w') as f:
            json.dump(llm_results, f)
    except:
        pass



# Summarize what is happening in the video clip in one sentence. Here are some examples:
# A man Y touches a cup on a table with his left hand.
# The man B taps on the card with his right hand.
# The man Y raised his left hand.
# The man X wipes his face with his left hand.