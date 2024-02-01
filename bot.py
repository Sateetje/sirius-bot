#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import json
import os
from copy import copy
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import datetime
import base64
import time
import asyncio

import validators

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

_port = int(os.environ["PORT"])
_webhook = os.environ["WEB_HOOK"]
_token = os.environ["BOT_TOKEN"]
_location = os.environ["URL_LOCATION"]
_certificate = os.environ["CERTIFICATE"]
_listen = "0.0.0.0"
RUN_NOW = os.getenv("RUN_NOW", 'False').lower() in ('true', '1', 't')

auth = [514304411,]
monitoring_chat = 514304411

old = {
    'height': 0,
    'ts': 0,
    'report': 0,
}

# Debug
#report_interval = 30
#min_report_age = 0
#validators_chat = 514304411

# Production
report_interval = 5600
min_report_age = 60 * 121
validators_chat = -1001223648019 # ProximaX Network Participants

max_age = 600

from xpxchain import models
from xpxchain import client

ENDPOINTS = [
    'arcturus.xpxsirius.io:3000',
    'aldebaran.xpxsirius.io:3000',
    'betelgeuse.xpxsirius.io:3000',
    'bigcalvin.xpxsirius.io:3000',
    'delphinus.xpxsirius.io:3000',
    'lyrasithara.xpxsirius.io:3000',
]

NETWORK_TYPE = models.NetworkType.MAIN_NET


def error(bot, update, error):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, error)

def report(bot, update):
    if (update.message.chat.id not in auth):
        return

    start_at = int(update.message.text.split()[1])
    report, last_block, diff, count = asyncio.run(validators.report(start_at = start_at, short = True))
    try:
        bot.send_message(update.message.chat.id, report, parse_mode = "Markdown")
        bot.send_message(update.message.chat.id, "```\n%d / %d (diff / real count)```" % (diff, count), parse_mode = "Markdown")
    except Exception as e:
        logger.warn("Exception: %s" % e)


async def check(endpoint, network_type=None):
    async with client.AsyncBlockchainHTTP(endpoint, network_type=network_type) as http:
        height = await http.get_blockchain_height()
        score = await http.get_blockchain_score()

        return endpoint, height, score.score


async def get_best():
    results = await asyncio.gather(*(check(ep, NETWORK_TYPE) for ep in ENDPOINTS))
    return results


def monitoring(context):
    global old

    logger.info("Job started")

#    f = open('/mnt/disk1/public-mainnet-peer-package/data/index.dat', 'rb')
#    v = f.read()
#    height = int.from_bytes(v, 'little')
#    f.close()

    ts = time.time()

#    if ((old['height'] == height) and (ts - old['ts'] > max_age)):
#        context.bot.send_message(monitoring_chat, 'Chain height %d is more then %ds old' % (height, max_age))
#    elif (height > old['height']):
#        old['height'] = height
#        old['ts'] = ts
    
    try:
        f = open('/data/report.dat', 'r')
        last_report = int(f.read()) + 1
        f.close()
    except Exception as e:
        logger.warn("Exception: %s" % e)
        return
    
    results = asyncio.run(get_best())
    results.sort(key=lambda x: x[2], reverse=True)

    logger.info("Endpoints: %s" % results)

    with client.BlockchainHTTP(results[0][0], network_type=NETWORK_TYPE) as http:
        block_1 = http.get_block_by_height(last_report)
        logger.info(block_1.timestamp)
    
    td = ts - (block_1.timestamp + models.TIMESTAMP_NEMESIS_BLOCK) / 1000
    #logger.info("Local chain height is %d." % (height))
    logger.info("Blockchain height is %d. Report is %d blocks old and %d sec old." % (results[0][1], results[0][1] - last_report, td))

    if ((ts - old['report'] > min_report_age) and (RUN_NOW or (datetime.datetime.now(datetime.timezone.utc).hour == 8))):
        report, last_block, diff, count = asyncio.run(validators.report(start_at = last_report, short = True, host = results[0][0]))
        for chat in [monitoring_chat, validators_chat]:
            if ((chat != monitoring_chat) and (diff != count)):
                continue

            try:
                context.bot.send_message(chat, report, parse_mode = "Markdown")
            except Exception as e:
                logger.warn("Exception: %s" % e)

            if ((chat == monitoring_chat) and (diff != count)):
                try:
                    context.bot.send_message(chat, "```\n%d / %d (diff / real count)```" % (diff, count), parse_mode = "Markdown")
                except Exception as e:
                    logger.warn("Exception: %s" % e)

        old['report'] = ts

        if (diff == count):
            f = open('/data/report.dat', 'w')
            f.write("%d" % last_block)
            f.close()
    
def main():
    updater = None

    i = 0
    while i < 2:
        try:
            # Create the EventHandler and pass it your bot's token.
            updater = Updater(_token, workers = 1)

            logger.info("Starting webhook '%s' %d '%s'" % (_listen, _port, _location))
            updater.start_webhook(listen=_listen, port=_port, url_path=_location, webhook_url=_webhook)
            #logger.info("Setting webhook '%s" % (_webhook))
            #updater.bot.set_webhook(url=_webhook, certificate=open(_certificate, 'rb'), timeout = 2000)
            break
        except Exception as e:
            logger.warn("Exception: %s" % e)
            if (updater):
                updater.stop()
                del updater
        #endtry
        
        i += 1
        time.sleep(1)
    #endwhile

    if (not updater):
        logger.error("Could not start updater")
        return

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("report", report))

    job = updater.job_queue
    logger.info("Starting job")
    job_sec = job.run_repeating(monitoring, interval=60, first=1)

    # log all errors
    #dp.add_error_handler(error)

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    logger.info("Running")
    updater.idle()

    logger.info("Stoping updater") 
    updater.stop()
 
if __name__ == '__main__':
    main()
