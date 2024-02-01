FROM python:3.7.3
RUN pip install python-telegram-bot==13.4.1 urllib3==1.26.16 asyncio httpx requests redis xpx-chain
ADD bot.py . validators.py . 
CMD ["python", "./bot.py"]
