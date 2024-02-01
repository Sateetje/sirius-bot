#!/usr/bin/python

import httpx
import asyncio
import json
import requests
import redis
from urllib.parse import urlparse

import logging
logging.basicConfig(format='[%(filename)s:%(lineno)d] %(levelname)s: %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

stats = {}
start = 1
count = 0
blocks = []
again = []
idx = 0
total = 0
rlb = 0 # Real last block
mains = []
accounts = []
queries = []
blacklist = []
checklist = []

def parse_reply(reply, first_block, stop):
    global stats, count, rlb, checklist

    for block in reply:
        height = block['block']['height'][0]
        if (height < first_block):
            continue
        if (height > stop):
            break
        if (block['block']['height'][0] in checklist):
            continue

        if (rlb < height):
            rlb = height

        signer = block['block']['signer']
        try:
            stats[signer]['count'] += 1
            stats[signer]['fees'] += block['meta']['totalFee'][0]
            stats[signer]['txs'] += block['meta']['numTransactions']
            if (block['meta']['totalFee'][0]):
                stats[signer]['nonempty'] += 1
        except KeyError:
            stats[signer] = {'count': 1, 'fees': block['meta']['totalFee'][0], 'txs': block['meta']['numTransactions'], 'nonempty': 0, 'atts': 0}
            if (block['meta']['totalFee'][0]):
                stats[signer]['nonempty'] += 1

        if (block['meta']['totalFee'][0] > 0):
            blocks.append(block['block']['height'][0])
        
        count += 1
        checklist.append(block['block']['height'][0])


async def get_block(host, first_block, stop):
    global queries, blacklist

    while (queries):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                while (queries):
                    start, limit = queries.pop()

                    url = "http://%s/blocks/%d/limit/%d" % (host, start, limit)
                    logger.info(url)

                    reply = None

                    reply = await client.get(url)
                    reply = json.loads(reply.text)

                    if ((not reply) or (len(reply) == 0)):
                        logger.warning("Empty response: '%s'" % url)
                        queries.append((start, limit))
                        break

                    try:    
                        parse_reply(reply, first_block, stop)
                    except Exception as e:
                        logger.exception('Error parsing reply (%s)' % url)
                        queries.append((start, limit))
                        break
        except Exception as e:
            logger.exception("Error while getting block (%s)" % url)
            queries.append((start, limit))
            continue

async def get_account(host):
    global accounts, total, stats, mains, blacklist

    while (accounts):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                while (accounts):
                    signer = accounts.pop()
                    stats[signer]['stake'] = 0
                    url = "http://%s/account/%s" % (host, signer)

                    logger.info(url)
                    reply = None

                    reply = await client.get(url)
                    reply = json.loads(reply.text)
                    
                    if ((not reply) or (len(reply) == 0)):
                        logger.warning("Empty response: '%s'" % url)
                        accounts.append(signer)
                        break
                  
                    if (('code' in reply) and (reply['code'] == 'ResourceNotFound')):
                        logger.warning("%s" % reply['message'])
                        accounts.append(signer)
                        break

                    main = remote = None
                    stats[signer]['type'] = reply['account']['accountType']
                    
                    if (reply['account']['accountType'] == 2):
                        url = "http://%s/account/%s" % (host, reply['account']['linkedAccountKey'])
                    
                        reply = await client.get(url)
                        reply = json.loads(reply.text)
                        
                        if ((not reply) or (len(reply) == 0)):
                            logger.warning("Empty response: '%s'" % url)
                            accounts.append(signer)
                            break
                      
                        if (('code' in reply) and (reply['code'] == 'ResourceNotFound')):
                            logger.warning("%s" % reply['message'])
                            accounts.append(signer)
                            break

                        remote = signer
                        main = reply['account']['publicKey']
                    elif (reply['account']['accountType'] == 1):
                        main = signer
                        remote = reply['account']['linkedAccountKey']
                    elif (reply['account']['accountType'] == 0):
                        main = signer

                    url = "http://%s/account/%s/multisig" % (host, signer)
                    r = await client.get(url)
                    
                    if (not reply):
                        logger.warning("Empty response: '%s'" % url)
                        accounts.append(signer)
                        break
                  
                    if (r.status_code == 200):
                        stats[signer]['multisig'] = True
                    else:
                        stats[signer]['multisig'] = False


                    for mosaic in reply['account']['mosaics']:
                        if ((mosaic['id'][0] == 2679028825) and (mosaic['id'][1] == 1076571991)):
                            b = mosaic['amount'][0].to_bytes(4, 'little') + mosaic['amount'][1].to_bytes(4, 'little')
                            amount = int.from_bytes(b, 'little') / 1000000
                            
                            if (main not in mains):
                                total += amount
                                mains.append(main)

                            stats[signer]['stake'] = amount
                            break
        except exception as e:
            logger.exception('error while getting account \'%s\'' % url)
            accounts.append(signer)
            continue


async def report(start_at = 1, stop = 0, last = 0, short = False, limit = 100, cb = None, host = None):
    global start, stats, count, blocks, again, idx, total, rlb, mains, accounts, queries, blacklist, checklist

    stats = {}
    count = 0
    blocks = []
    again = []
    idx = 0
    total = 0
    rlb = 0 # Real last block
    mains = []
    accounts = []
    queries = []
    blacklist = []
    checklist = []

    if not host:
        raise Exception('No endpoint provided')

    hosts = [ host ] 

    start = start_at

    for h in hosts:
        try:
            reply = requests.get('http://%s/chain/height' % h).json()
            logger.info(reply)
            last_block = reply['height'][0]
        except Exception as e:
            logger.error(e)

        if (last_block < start) or (last_block < last):
            continue
        else:
            break
    
    if (last != 0):
        stop = last_block
        start = stop - last
        first_block = start + 1
    else:   
        first_block = start

    if (stop == 0):
        stop = last_block

    start = int((start - 1) / limit) * limit + 1
    logger.info("Start: %d Stop: %d First: %d Last: %d" % (start, stop, first_block, last_block))

    while ((start < last_block) and (start < stop)):
        queries.append((start, limit))
        start += limit

    while (queries):
        await asyncio.gather(*(get_block(host, first_block, stop) for host in hosts))
        hosts = list(set(hosts) - set(blacklist))
        logger.info(hosts)
        if (not hosts):
            raise Exception('No more endpoints')

#    rdb = redis.Redis(host='localhost', port=6379, db=1)
#
#    collisions = rdb.smembers('blocks')
#
#    for block in collisions:
#        height, signer = block.decode('utf-8').split(':')
#        
#        try:
#            stats[signer]['atts'] += 1
#        except KeyError:
#            stats[signer] = {'count': 0, 'fees': 0, 'txs': 0, 'nonempty': 0, 'atts': 1}
#
#    rdb.delete('blocks')

    accounts = list(stats.keys())
    
    while (accounts):
        await asyncio.gather(*(get_account(host) for host in hosts))
        hosts = list(set(hosts) - set(blacklist)) 
        if (not hosts):
            raise Exception('No more endpoints')

    diff = rlb - first_block + 1
    logger.info("First: %d Last: %d Diff: %d Count: %d" % (first_block, rlb, diff, count))

    accounts = list(stats.keys())
    accounts.sort(key = lambda x: stats[x]['count'], reverse = True)
    
    reply = "#validators\n"
    reply += "\n"
    reply += "```\n"
    reply += "Height: %d - %d\n" % (first_block, rlb)
    reply += "Blocks: %d blocks\n" % (diff)
    reply += "Staked: {:,} XPX\n".format(int(total))
    reply += "     #: {:,} validators\n".format(len(accounts))
    reply += "\n"
    reply += "Signer Blocks Fees Stake\n"
    
    for signer in accounts:
        row = stats[signer] 
        reply += "%s %6d %4d %4.1fM%s%s\n" % (
            short and signer[:6] or signer, 
            row['count'], 
            #row['nonempty'], 
            #row['txs'], 
            row['fees'] / 1000000, row['stake'] / 1000000, 
            row['type'] == 2 and '*' or '',
            row['multisig'] == True and '~' or '',
        )
    
    reply += "\n"
    reply += "* Delegated account\n"
    reply += "~ Multisig account\n"
    reply += "```"

    logger.info(reply)

    if (cb):
        cb()

    return (reply, rlb, diff, count)

