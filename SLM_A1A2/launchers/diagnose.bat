@echo off
"C:\Users\Kevin\Desktop\code\U\IA\SLM_A1A2\.venv\Scripts\python.exe" -c "import torch,transformers;print('torch:',torch.__version__);print('transformers:',transformers.__version__);print('CUDA:',torch.cuda.is_available());print('GPU:',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU');print('BF16:',torch.cuda.is_bf16_supported() if torch.cuda.is_available() else False)"
nvidia-smi
pause
