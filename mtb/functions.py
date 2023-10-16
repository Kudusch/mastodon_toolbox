#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from requests.exceptions import ConnectTimeout
from urllib.parse import urlparse
import configparser
import csv
import json
import logging
import mastodon
import os
import re
import requests
import sys
import time
import warnings
from pathlib import Path
from shutil import get_terminal_size

# ignore MarkupResemblesLocatorWarning
warnings.filterwarnings("ignore", category=UserWarning, module="bs4")

logger = logging.getLogger(__name__)
file_handler = logging.FileHandler("mastodon-tb.log")
formatter = logging.Formatter(
    "[%(levelname)s] | %(asctime)s | %(message)s",
    "%Y-%m-%dT%H:%M:%S"
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.setLevel(logging.INFO)

key_names = ["id", "created_at", "edited_at", "content", "reblog", "sensitive", "spoiler_text", "visibility", "replies_count", "reblogs_count", "favourites_count", "language", "in_reply_to_id", "in_reply_to_account_id", "user_id", "user_name", "user_acct", "user_locked", "user_bot", "user_discoverable", "user_group", "user_created_at", "user_note", "user_url", "user_avatar", "user_header", "user_followers_count", "user_following_count", "user_statuses_count", "user_last_status_at", "user_emojis", "user_fields", "media_id", "media_type", "media_url", "media_preview_url", "media_remote_url", "media_preview_remote_url", "media_text_url", "media_meta", "media_description", "media_blurhash", "mentions_id", "mentions_username", "mentions_url", "mentions_acct", "hashtags", "card_url", "card_title", "card_description", "card_type", "card_author_name", "card_author_url", "card_provider_name", "card_provider_url", "card_html", "card_width", "card_height", "card_image", "card_embed_url", "card_blurhash", "poll_id", "poll_expires_at", "poll_expired", "poll_multiple", "poll_votes_count", "poll_voters_count", "poll_options", "poll_votes", "uri", "url", "instance_name", "queried_at"]

account_key_names = ["id", "username", "acct", "display_name", "locked", "bot", "discoverable", "group", "created_at", "note", "url", "avatar",
                     "avatar_static", "header", "header_static", "followers_count", "following_count", "statuses_count", "last_status_at", "emojis", "fields", "queried_at"]

instance_key_names = ["uri", "title", "short_description", "description", "email", "version", "user_count", "status_count", "domain_count", "weekly_statuses", "weekly_logins", "weekly_registrations", "thumbnail", "languages", "registrations", "approval_required", "invites_enabled", "max_characters", "max_media_attachments", "max_poll_options", "max_poll_characters_per_option", "contact_account_url", "rules"]

trends_key_names = {
    "tags": ["name", "url"],
    "links": ["url", "title", "description", "type", "author_name", "author_url", "provider_name", "provider_url", "html", "width", "height", "image", "embed_url", "blurhash"]
}

USER_AGENT = "mastodon_toolbox/1.0 (+https://github.com/Kudusch/mastodon_toolbox)"

config = configparser.ConfigParser()
config.read(Path(__file__).parents[5].joinpath("config.ini"))
access_tokens = config["MASTODON"]


def get_datetime_range(toots):
    values = [t["created_at"] for t in toots]
    return (f"created_at from {min(values):%Y-%m-%d %H:%M} to {max(values):%Y-%m-%d %H:%M}")


def parse_toot_html(html):
    toot_content = BeautifulSoup(html, "html.parser")
    for e in toot_content.find_all(["p", "br"]):
        e.append('\n')
    return toot_content.text


def acct_to_string(acct):
    if "acct" in acct.keys() and "url" in acct.keys():
        if not "@" in acct["acct"]:
            regex = r"https?:\/\/(.*?)\/@(.*)"
            try:
                instance, name = re.search(
                    regex, acct["url"], re.MULTILINE).groups()
                return f"{name}@{instance}"
            except:
                return acct["url"]
        else:
            return acct["acct"]
    else:
        return ""


def get_home_instance(toot):
    instance = toot["uri"].split("/")
    return instance[2]


def get_home_id(toot):
    home_id = re.search("\d+$", toot["uri"]).group(0)
    return home_id


def add_queried_at(toots):
    queried_at = datetime.now()
    for toot in toots:
        toot["queried_at"] = queried_at
    return toots


def aggregate_timelines(files):
    unique_toots = {}
    for fname in files:
        with open(f"{fname}", "r") as f:
            for instance, toots in json.load(f).items():
                if not toots:
                    continue
                for toot in toots:
                    if toot["uri"] in unique_toots:
                        unique_toots[toot["uri"]].append((instance, toot))
                    else:
                        unique_toots[toot["uri"]] = [(instance, toot)]

    for uri, toots in unique_toots.items():
        if len(toots) == 1:
            instance, toot = toots[0]
            instance = f"[\"{instance}\"]"
            toot["id"] = uri
        else:
            instances = [i for i, t in toots]
            toot = sorted([t for i, t in toots], key=lambda t: (
                t["replies_count"]+t["reblogs_count"]+t["favourites_count"]), reverse=True)[0]
            instance = json.dumps(instances)
            toot["id"] = uri
        yield instance, uri, toot


def filter_toots(toots, query=None, notes_tags=["nosearch", "nobots", "noindex", "nobot"]):
    if not toots:
        return toots
    pre_n = len(toots)
    if query:
        toots = [t for t in toots if query in t["content"]]
    if notes_tags:
        regex = re.compile(
            f"#<span>({'|'.join(notes_tags)})<\/span>", re.IGNORECASE)
        filtered_toots = []
        for toot in toots:
            if toot["account"]["note"] == "":
                filtered_toots.append(toot)
            elif not regex.search(re.escape(toot["account"]["note"])):
                filtered_toots.append(toot)
        toots = filtered_toots
    return toots


def format_snowflake(sf):
    if (isinstance(sf, datetime)):
        return (f"{sf:%Y-%m-%d}/{(int(sf.timestamp()) * 1000) << 16}")
    else:
        return (f"{datetime.fromtimestamp((int(sf)>>16)/1000):%Y-%m-%d}/{int(sf)}")

# check moved_to


def sanitize_toot(raw_toot, instance_name=None, parse_html=False):
    toot = {
        "id": raw_toot["id"],
        "in_reply_to_id": raw_toot["in_reply_to_id"],
        "in_reply_to_account_id": raw_toot["in_reply_to_account_id"],
        "sensitive": raw_toot["sensitive"],
        "spoiler_text": raw_toot["spoiler_text"],
        "visibility": raw_toot["visibility"],
        "language": raw_toot["language"],
        "uri": raw_toot["uri"],
        "url": raw_toot["url"],
        "replies_count": raw_toot["replies_count"],
        "reblogs_count": raw_toot["reblogs_count"],
        "favourites_count": raw_toot["favourites_count"],
        "reblog": raw_toot["reblog"],
    }

    if parse_html:
        try:
            toot["content"] = parse_toot_html(raw_toot["content"])
        except MarkupResemblesLocatorWarning:
            pass
        except:
            toot["content"] = raw_toot["content"]
    else:
        toot["content"] = raw_toot["content"]

    try:
        toot["created_at"] = format(
            raw_toot["created_at"], "%Y-%m-%dT%H:%M:%S")
    except:
        toot["created_at"] = raw_toot["created_at"]
    if "edited_at" in raw_toot.keys() and raw_toot["edited_at"] is not None:
        try:
            toot["edited_at"] = datetime.strptime(
                f"{raw_toot['edited_at']} -0000", "%Y-%m-%dT%H:%M:%S.%fZ %z")
            toot["edited_at"] = format(toot["edited_at"], "%Y-%m-%dT%H:%M:%S")
        except:
            toot["edited_at"] = raw_toot["edited_at"]
    else:
        toot["edited_at"] = ""

    toot["user_id"] = raw_toot["account"]["id"]
    toot["user_name"] = raw_toot["account"]["display_name"]
    toot["user_acct"] = raw_toot["account"]["acct"]
    toot["user_locked"] = raw_toot["account"]["locked"]
    toot["user_bot"] = raw_toot["account"]["bot"]
    try:
        toot["user_discoverable"] = raw_toot["account"]["discoverable"]
    except:
        toot["user_discoverable"] = ""
    try:
        toot["user_group"] = raw_toot["account"]["group"]
    except:
        toot["user_group"] = ""

    try:
        toot["user_created_at"] = format(
            raw_toot["account"]["created_at"], "%Y-%m-%dT%H:%M:%S")
    except:
        toot["user_created_at"] = raw_toot["account"]["created_at"].replace(
            ".000Z", "")
    toot["user_note"] = raw_toot["account"]["note"]
    toot["user_url"] = raw_toot["account"]["url"]
    toot["user_avatar"] = raw_toot["account"]["avatar"]
    toot["user_header"] = raw_toot["account"]["header"]
    toot["user_followers_count"] = raw_toot["account"]["followers_count"]
    toot["user_following_count"] = raw_toot["account"]["following_count"]
    toot["user_statuses_count"] = raw_toot["account"]["statuses_count"]
    try:
        try:
            toot["user_last_status_at"] = format(
                raw_toot["account"]["last_status_at"], "%Y-%m-%dT%H:%M:%S")
        except:
            toot["user_last_status_at"] = raw_toot["account"]["last_status_at"].replace(
                ".000Z", "")
    except:
        toot["user_last_status_at"] = ""
    toot["user_emojis"] = json.dumps(raw_toot["account"]["emojis"])
    toot["user_fields"] = json.dumps(raw_toot["account"]["fields"])

    list_id = []
    list_type = []
    list_url = []
    list_preview_url = []
    list_remote_url = []
    list_preview_remote_url = []
    list_text_url = []
    list_meta = []
    list_description = []
    list_blurhash = []
    for media in raw_toot["media_attachments"]:
        list_id.append(media["id"])
        list_type.append(media["type"])
        list_url.append(media["url"])
        list_preview_url.append(media["preview_url"])
        list_remote_url.append(media["remote_url"])
        try:
            list_preview_remote_url.append(media["preview_remote_url"])
        except:
            list_preview_remote_url.append("")
        list_text_url.append(media["text_url"])
        try:
            list_meta.append(media["meta"])
        except:
            list_meta.append("")
        list_description.append(media["description"])
        try:
            list_blurhash.append(media["blurhash"])
        except:
            list_blurhash.append("")

    toot["media_id"] = json.dumps(list_id)
    toot["media_type"] = json.dumps(list_type)
    toot["media_url"] = json.dumps(list_url)
    toot["media_preview_url"] = json.dumps(list_preview_url)
    toot["media_remote_url"] = json.dumps(list_remote_url)
    toot["media_preview_remote_url"] = json.dumps(list_preview_remote_url)
    toot["media_text_url"] = json.dumps(list_text_url)
    toot["media_meta"] = json.dumps(list_meta)
    toot["media_description"] = json.dumps(list_description)
    toot["media_blurhash"] = json.dumps(list_blurhash)

    list_id = []
    list_username = []
    list_url = []
    list_acct = []
    for mention in raw_toot["mentions"]:
        list_id.append(mention["id"])
        list_username.append(mention["username"])
        list_url.append(mention["url"])
        list_acct.append(mention["acct"])

    toot["mentions_id"] = json.dumps(list_id)
    toot["mentions_username"] = json.dumps(list_username)
    toot["mentions_url"] = json.dumps(list_url)
    toot["mentions_acct"] = json.dumps(list_acct)

    toot["hashtags"] = json.dumps([hashtag["name"]
                                  for hashtag in raw_toot["tags"]])

    if raw_toot["card"] is not None:
        toot["card_url"] = raw_toot["card"]["url"]
        toot["card_title"] = raw_toot["card"]["title"]
        toot["card_description"] = raw_toot["card"]["description"]
        toot["card_type"] = raw_toot["card"]["type"]
        try:
            toot["card_author_name"] = raw_toot["card"]["author_name"]
        except:
            toot["card_author_name"] = ""
        toot["card_author_url"] = raw_toot["card"]["author_url"]
        toot["card_provider_name"] = raw_toot["card"]["provider_name"]
        toot["card_provider_url"] = raw_toot["card"]["provider_url"]
        try:
            toot["card_html"] = raw_toot["card"]["html"]
        except:
            toot["card_html"] = ""
        toot["card_width"] = raw_toot["card"]["width"]
        toot["card_height"] = raw_toot["card"]["height"]
        toot["card_image"] = raw_toot["card"]["image"]
        try:
            toot["card_embed_url"] = raw_toot["card"]["embed_url"]
        except:
            toot["card_embed_url"] = ""
        try:
            toot["card_blurhash"] = raw_toot["card"]["blurhash"]
        except:
            toot["card_blurhash"] = ""
    else:
        toot["card_url"] = ""
        toot["card_title"] = ""
        toot["card_description"] = ""
        toot["card_type"] = ""
        toot["card_author_name"] = ""
        toot["card_author_url"] = ""
        toot["card_provider_name"] = ""
        toot["card_provider_url"] = ""
        toot["card_html"] = ""
        toot["card_width"] = ""
        toot["card_height"] = ""
        toot["card_image"] = ""
        toot["card_embed_url"] = ""
        toot["card_blurhash"] = ""

    if raw_toot["poll"] is not None:
        toot["poll_id"] = raw_toot["poll"]["id"]
        try:
            toot["poll_expires_at"] = format(
                raw_toot["poll"]["expires_at"], "%Y-%m-%dT%H:%M:%S")
        except:
            toot["poll_expires_at"] = ""
        toot["poll_expired"] = raw_toot["poll"]["expired"]
        toot["poll_multiple"] = raw_toot["poll"]["multiple"]
        toot["poll_votes_count"] = raw_toot["poll"]["votes_count"]
        toot["poll_voters_count"] = raw_toot["poll"]["voters_count"]
        toot["poll_options"] = json.dumps(
            [option["title"] for option in raw_toot["poll"]["options"]])
        toot["poll_votes"] = json.dumps(
            [option["votes_count"] for option in raw_toot["poll"]["options"]])
    else:
        toot["poll_id"] = ""
        toot["poll_expires_at"] = ""
        toot["poll_expired"] = ""
        toot["poll_multiple"] = ""
        toot["poll_votes_count"] = ""
        toot["poll_voters_count"] = ""
        toot["poll_options"] = ""
        toot["poll_votes"] = ""

    if "queried_at" in raw_toot.keys():
        try:
            toot["queried_at"] = format(
                raw_toot["queried_at"], "%Y-%m-%dT%H:%M:%S")
        except:
            toot["queried_at"] = raw_toot["queried_at"].replace(".000Z", "")
    else:
        toot["queried_at"] = ""

    if instance_name is not None:
        toot["instance_name"] = instance_name
    else:
        toot["instance_name"] = ""

    return toot


def instances_to_lines(queried_instances, parse_html=False, verbose=False):
    lines = []
    if verbose and logger.level >= 20:
        logger.setLevel(logging.INFO)

    if queried_instances:
        for instance_name, data in queried_instances.items():
            instance_info = data["instance"]
            activity = data["activity"]
            queried_at = data["queried_at"]
            instance = {}
            try:
                instance["uri"] = instance_info["uri"]
            except:
                instance["uri"] = instance_name

            try:
                instance["title"] = instance_info["title"]
            except:
                instance["title"] = ""

            try:
                instance["short_description"] = instance_info["short_description"]
                if parse_html:
                    instance["short_description"] = parse_toot_html(
                        instance["short_description"])
            except:
                instance["short_description"] = ""

            try:
                instance["description"] = instance_info["description"]
                if parse_html:
                    instance["description"] = parse_toot_html(
                        instance["description"])
            except:
                instance["description"] = ""

            try:
                instance["email"] = instance_info["email"]
            except:
                instance["email"] = ""

            try:
                instance["version"] = instance_info["version"]
            except:
                instance["version"] = ""

            try:
                instance["user_count"] = instance_info["stats"]["user_count"]
            except:
                instance["user_count"] = ""

            try:
                instance["status_count"] = instance_info["stats"]["status_count"]
            except:
                instance["status_count"] = ""

            try:
                instance["domain_count"] = instance_info["stats"]["domain_count"]
            except:
                instance["domain_count"] = ""

            try:
                instance["weekly_statuses"] = int(
                    sum([a["statuses"] for a in activity[1:]])/len(activity[1:]))
                instance["weekly_logins"] = int(
                    sum([a["logins"] for a in activity[1:]])/len(activity[1:]))
                instance["weekly_registrations"] = int(
                    sum([a["registrations"] for a in activity[1:]])/len(activity[1:]))
            except:
                instance["weekly_statuses"] = ""
                instance["weekly_logins"] = ""
                instance["weekly_registrations"] = ""

            try:
                instance["thumbnail"] = instance_info["thumbnail"]
            except:
                instance["thumbnail"] = ""

            try:
                instance["languages"] = json.dumps(instance_info["languages"])
            except:
                instance["languages"] = ""

            try:
                instance["registrations"] = instance_info["registrations"]
            except:
                instance["registrations"] = ""

            try:
                instance["approval_required"] = instance_info["approval_required"]
            except:
                instance["approval_required"] = ""

            try:
                instance["invites_enabled"] = instance_info["invites_enabled"]
            except:
                instance["invites_enabled"] = ""

            try:
                instance["max_characters"] = instance_info["configuration"]["statuses"]["max_characters"]
                instance["max_media_attachments"] = instance_info["configuration"]["statuses"]["max_media_attachments"]
                instance["max_poll_options"] = instance_info["configuration"]["polls"]["max_options"]
                instance["max_poll_characters_per_option"] = instance_info["configuration"]["polls"]["max_characters_per_option"]
            except:
                instance["max_characters"] = ""
                instance["max_media_attachments"] = ""
                instance["max_poll_options"] = ""
                instance["max_poll_characters_per_option"] = ""

            try:
                instance["contact_account_url"] = instance_info["contact_account"]["url"]
            except:
                instance["contact_account_url"] = ""

            try:
                instance["rules"] = json.dumps(instance_info["rules"])
            except:
                instance["rules"] = ""

            try:
                lines.append([instance[k] for k in instance_key_names])
            except Exception as e:
                logger.error(f"Error sanitizing instance: {str(e)}")
    if verbose and logger.level >= 20:
        logger.setLevel(logging.WARNING)
    return lines


def accounts_to_lines(queried_accounts, parse_html=False, verbose=False):
    lines = []
    if verbose and logger.level >= 20:
        logger.setLevel(logging.INFO)

    if queried_accounts:
        for account in queried_accounts:
            try:
                account["emojis"] = json.dumps(account["emojis"])
                account["fields"] = json.dumps(account["fields"])
                if parse_html:
                    account["note"] = parse_toot_html(account["note"])
                lines.append([account[k] for k in account_key_names])
            except Exception as e:
                logger.error(f"Error sanitizing account: {str(e)}")
    if verbose and logger.level >= 20:
        logger.setLevel(logging.WARNING)
    return lines


def toots_to_lines(queried_toots, parse_html=False, instance_name=None, verbose=False):
    lines = []
    if verbose and logger.level >= 20:
        logger.setLevel(logging.INFO)

    if queried_toots:
        for toot in queried_toots:
            if type(toot) is list:
                for t in toot:
                    try:
                        sanitized_toot = sanitize_toot(
                            t, parse_html=parse_html, instance_name=instance_name)
                        lines.append([sanitized_toot[k] for k in key_names])
                    except Exception as e:
                        logger.error(f"Error sanitizing toot: {str(e)}")

            else:
                try:
                    sanitized_toot = sanitize_toot(
                        toot, parse_html=parse_html, instance_name=instance_name)
                    lines.append([sanitized_toot[k] for k in key_names])
                except Exception as e:
                    logger.error(f"Error sanitizing toot: {str(e)}")
    if verbose and logger.level >= 20:
        logger.setLevel(logging.WARNING)
    return lines


def toots_to_csv(queried_toots, file_name, parse_html=False, instance_name=None, append=False, verbose=False):
    if verbose and logger.level >= 20:
        logger.setLevel(logging.INFO)

    file_mode = "a+" if append else "w"
    if append:
        logger.info(f"Appending to {file_name}")
    else:
        logger.info(f"Writing to {file_name}")
        if os.path.isfile(file_name):
            logger.warning(f"Overwriting existing file!")

    if queried_toots:
        with open(file_name, file_mode, newline='') as f:
            writer = csv.writer(f, dialect="unix")
            if not append:
                writer.writerow(key_names)
            elif append and os.path.getsize(file_name) == 0:
                writer.writerow(key_names)
            parsed_toots = toots_to_lines(
                queried_toots, parse_html=parse_html, instance_name=instance_name)
            for toot in parsed_toots:
                writer.writerow(toot)
        logger.info(f"{len(queried_toots)} toots written")
    else:
        logger.warning(f"No toots to write to file")

    if verbose and logger.level >= 20:
        logger.setLevel(logging.WARNING)


def get_toots_reblogs(toots, request_timeout=15, verbose=False):
    if verbose and logger.level >= 20:
        logger.setLevel(logging.INFO)

    reblogs = {}

    if not toots:
        logger.warning(f"No toots provided, nothing to do")
        return reblogs

    for t in toots:
        reblogs[t["uri"]] = {
            "reblogs": [],
            "source": None
        }

        try:
            api_base = get_home_instance(t)
            home_id = get_home_id(t)
            api = mastodon.Mastodon(api_base_url=api_base, access_token=None,
                                    request_timeout=request_timeout, user_agent=USER_AGENT)
        except:
            logger.warning(f"Issues with {t['uri']}")
            reblogs[t["uri"]]["source"] = "error"
            next

        try:
            reblogs[t["uri"]]["source"] = api.status(home_id)
        except:
            reblogs[t["uri"]]["source"] = "deleted"

        try:
            new_page = api.status_reblogged_by(home_id)
            if new_page:
                reblogs[t["uri"]]["reblogs"].extend(new_page)
            while new_page:
                new_page = api.fetch_next(new_page)
                if new_page:
                    reblogs[t["uri"]]["reblogs"].extend(new_page)
        except:
            pass

        logger.info(
            f"Retrieved {len(reblogs[t['uri']]['reblogs'])} reblogs for {t['uri']}")

    if verbose and logger.level >= 20:
        logger.setLevel(logging.WARNING)

    return reblogs


def get_toots_favourites(toots, request_timeout=15, verbose=False):
    if verbose and logger.level >= 20:
        logger.setLevel(logging.INFO)

    favs = {}

    if not toots:
        logger.warning(f"No toots provided, nothing to do")
        return favs

    for t in toots:
        favs[t["uri"]] = {
            "favourites": [],
            "source": None
        }

        try:
            api_base = get_home_instance(t)
            home_id = get_home_id(t)
            api = mastodon.Mastodon(api_base_url=api_base, access_token=None,
                                    request_timeout=request_timeout, user_agent=USER_AGENT)
        except:
            logger.warning(f"Issues with {t['uri']}")
            favs[t["uri"]]["source"] = "error"
            next

        try:
            favs[t["uri"]]["source"] = api.status(home_id)
        except:
            favs[t["uri"]]["source"] = "deleted"

        try:
            new_page = api.status_favourited_by(home_id)
            if new_page:
                favs[t["uri"]]["favourites"].extend(new_page)
            while new_page:
                new_page = api.fetch_next(new_page)
                if new_page:
                    favs[t["uri"]]["favourites"].extend(new_page)
        except:
            pass

        logger.info(
            f"Retrieved {len(favs[t['uri']]['favourites'])} favourites for {t['uri']}")

    if verbose and logger.level >= 20:
        logger.setLevel(logging.WARNING)

    return favs


def get_toots_context(toots, request_timeout=15, save_toots=False, parse_html=False, verbose=False):
    if verbose and logger.level >= 20:
        logger.setLevel(logging.INFO)

    context = {}

    if not toots:
        logger.warning(f"No toots provided, nothing to do")
        return context

    for t in toots:
        context[t["uri"]] = {
            "ancestors": [],
            "descendants": [],
            "source": None
        }

        try:
            api_base = get_home_instance(t)
            home_id = get_home_id(t)
            if api_base in access_tokens.keys():
                access_token = access_tokens[api_base]
            else:
                access_token = None
            api = mastodon.Mastodon(api_base_url=api_base, access_token=access_token, request_timeout=request_timeout, user_agent=USER_AGENT)
        except:
            logger.warning(f"Issues with {t['uri']}")
            context[t["uri"]]["source"] = "error"
            next

        try:
            context[t["uri"]]["source"] = api.status(home_id)
        except:
            context[t["uri"]]["source"] = "deleted"

        try:
            new_page = api.status_context(home_id)
            if new_page:
                context[t["uri"]]["ancestors"].extend(new_page["ancestors"])
                context[t["uri"]]["descendants"].extend(
                    new_page["descendants"])
            while new_page:
                new_page = api.fetch_next(new_page)
                if new_page:
                    context[t["uri"]]["ancestors"].extend(
                        new_page["ancestors"])
                    context[t["uri"]]["descendants"].extend(
                        new_page["descendants"])
        except:
            pass

        logger.info(
            f"Retrieved {len(context[t['uri']]['ancestors'])} ancestors and {len(context[t['uri']]['descendants'])} descendants for {t['uri']}")

    if save_toots:
        with open("context_toots.csv", "w") as f:
            writer = csv.writer(f, dialect="unix")
            writer.writerow(key_names + ["context_type"])
            for uri, context_toots in context.items():
                instance_name = urlparse(uri).netloc
                ancestors = context_toots["ancestors"]
                descendants = context_toots["descendants"]
                source = context_toots["source"]
                for toot in toots_to_lines(ancestors, parse_html=parse_html, instance_name=instance_name, verbose=False):
                    writer.writerow(toot + ["ancestor"])
                for toot in toots_to_lines(descendants, parse_html=parse_html, instance_name=instance_name, verbose=False):
                    writer.writerow(toot + ["descendant"])
                for toot in toots_to_lines([source], parse_html=parse_html, instance_name=instance_name, verbose=False):
                    writer.writerow(toot + ["source"])

    if verbose and logger.level >= 20:
        logger.setLevel(logging.WARNING)

    return context


def get_account_followers(account_url, max_followers=None, verbose=False, request_timeout=15):
    if verbose and logger.level >= 20:
        logger.setLevel(logging.INFO)

    api_base = urlparse(account_url).netloc
    api = mastodon.Mastodon(
        api_base_url=api_base, request_timeout=request_timeout, user_agent=USER_AGENT)
    account_name = account_url.split("@")[-1]
    account = api.search_v2(f"@{account_name}@{api_base}",
                            resolve=False, result_type="accounts")["accounts"][0]
    if max_followers:
        logger.info(
            f"Getting {max_followers} followers for {account['url']} ({account['followers_count']} followers)")
    else:
        max_followers = int(account['followers_count'])
        logger.info(
            f"Getting all followers for {account['url']} ({account['followers_count']} followers)")

    queried_accounts = []
    new_followers = api.account_followers(account["id"], limit=40)
    queried_accounts.extend(add_queried_at(new_followers))

    if len(new_followers) >= 40:
        paginate = True
    else:
        paginate = False
    while paginate:
        new_followers = api.fetch_next(new_followers)
        time.sleep(1.5)
        if new_followers:
            queried_accounts.extend(add_queried_at(new_followers))
            if len(queried_accounts) < max_followers and len(new_followers) > 0:
                logger.debug(
                    f"Retrieved {len(new_followers)} new followers and {len(queried_accounts)} followers in total")
            else:
                paginate = False
        else:
            paginate = False
    if max_followers:
        queried_accounts = queried_accounts[:max_followers]
    logger.info(f"Got {len(queried_accounts)} followers for {account['url']}")

    if verbose and logger.level >= 20:
        logger.setLevel(logging.WARNING)

    return queried_accounts


def get_accounts_by_url(urls, file_name=None, parse_html=False, request_timeout=15, verbose=False):
    if verbose and logger.level >= 20:
        logger.setLevel(logging.INFO)

    if not urls:
        logger.warning(f"No account urls supplied, exiting.")
        exit()

    accounts = []
    for i, url in enumerate(urls):
        try:
            api_base = urlparse(url).netloc
            api = mastodon.Mastodon(
                api_base_url=api_base, request_timeout=request_timeout, user_agent=USER_AGENT)
            account_name = url.split("@")[-1]
            account = api.search_v2(
                f"@{account_name}@{api_base}", resolve=False, result_type="accounts")["accounts"][0]
            accounts.append(account)
            logger.info(
                f"Retrieved info for @{account['acct']} \"{account['display_name']}\" ({account['followers_count']} follower, {account['statuses_count']} posts)")
            if verbose:
                message = f"Retrieved info for account {i+1} of {len(urls)}: @{account['acct']} ({account['followers_count']} follower, {account['statuses_count']} posts)"
                print(f'{message:{get_terminal_size().columns}.{get_terminal_size().columns}}', end="\r")
        except:
            logger.error(f"Error retrieving info for {url}")

    accounts = add_queried_at(accounts)
    if file_name and ".csv" in file_name:
        with open(file_name, "w") as f:
            writer = csv.writer(f, dialect="unix")
            writer.writerow(account_key_names)
            for account in accounts_to_lines(accounts, parse_html=parse_html):
                writer.writerow(account)

    logger.info(f"Retrieved {len(accounts)} accounts")
    return accounts


def get_instance_trends(api_base, access_token=None, verbose=False, request_timeout=30):
    if verbose and logger.level >= 20:
        logger.setLevel(logging.INFO)

    try:
        api = mastodon.Mastodon(api_base_url=api_base, access_token=access_token,
                                request_timeout=request_timeout, ratelimit_method="pace", user_agent=USER_AGENT)
        trends = {
            "tags": api.trending_tags(),
            "statuses": add_queried_at(api.trending_statuses()),
            "links": api.trending_links()
        }
        logger.info(f"Got trends for {api_base}")
    except:
        trends = None
        logger.warning(f"No trends for {api_base} found")

    # logger.handlers[0].flush()
    if verbose and logger.level >= 20:
        logger.setLevel(logging.WARNING)

    return trends


def get_instances_by_url(urls, file_name=None, include_peers=False, parse_html=False, request_timeout=15, verbose=False):
    if verbose and logger.level >= 20:
        logger.setLevel(logging.INFO)

    if not urls:
        logger.warning(f"No instance urls supplied, exiting.")
        exit()

    instances = {}
    for api_base in urls:
        if api_base in access_tokens.keys():
            access_token = access_tokens[api_base]
        else:
            access_token = None

        try:
            api = mastodon.Mastodon(api_base_url=api_base, request_timeout=request_timeout, access_token=access_token, user_agent=USER_AGENT)
            instance = api.instance()
        except:
            instance = None

        try:
            activity = api.instance_activity()
        except:
            activity = None

        instances[api_base] = {"instance": instance,
                               "activity": activity, "queried_at": datetime.now()}
        if instance:
            logger.info(
                f"Retrieved info for {api_base} ({instance['stats']['user_count']} users and {instance['stats']['status_count']} posts)")

    if file_name and ".csv" in file_name:
        with open(file_name, "w") as f:
            writer = csv.writer(f, dialect="unix")
            writer.writerow(instance_key_names)
            for instance in instances_to_lines(instances, parse_html=parse_html):
                writer.writerow(instance)

    logger.info(f"Retrieved {len(instances)} instances")
    return instances


def get_toots_by_url(urls, verbose=False):
    pass


def search_public(api_base, query=None, access_token=None, min_id=None, max_id=None, max_toots=None, local_only=False, verbose=False, request_timeout=30):
    if verbose and logger.level >= 20:
        logger.setLevel(logging.INFO)

    try:
        api = mastodon.Mastodon(api_base_url=api_base, access_token=access_token,
                            request_timeout=request_timeout, ratelimit_method="pace", user_agent=USER_AGENT)
    except:
        logger.warning(
            f"There was a problem connecting to {api_base}")
        return None

    if min_id and (not isinstance(min_id, datetime)):
        min_id = int(min_id)

    if max_id and (not isinstance(max_id, datetime)):
        max_id = int(max_id)

    queried_toots = []
    try:
        if min_id and not max_id:
            new_toots = api.timeline_public(
                limit=40, min_id=min_id, local=local_only)
        elif max_id and not min_id:
            new_toots = api.timeline_public(
                limit=40, max_id=max_id, local=local_only)
        queried_toots.extend(add_queried_at(new_toots))
    except mastodon.MastodonAPIError as e:
        logger.warning(
            f"There was a problem connecting to {api_base}: {e.args[1:]}")
        return None

    if len(queried_toots) == 0:
        logger.info(f"No toots with that hashtag found")

        if verbose and logger.level >= 20:
            logger.setLevel(logging.WARNING)
        return None

    if len(new_toots) >= 40 and len(queried_toots) < max_toots:
        paginate = True
    else:
        paginate = False
    while paginate:
        try:
            new_toots = api.fetch_previous(new_toots)
        except:
            new_toots = []
        if len(new_toots) > 0 and len(queried_toots) < max_toots:
            queried_toots.extend(add_queried_at(new_toots))
            logger.info(
                f"Got {len(queried_toots)} toots from {api_base} ({api.ratelimit_remaining} calls remaining, reset at {datetime.fromtimestamp(api.ratelimit_reset):%Y-%m-%d %H:%M:%S})")
        else:
            paginate = False

    logger.handlers[0].flush()
    if verbose and logger.level >= 20:
        logger.setLevel(logging.WARNING)

    return queried_toots


def search_hashtag(queried_hashtag, api_base, access_token=None, min_id=None, max_id=None, local_only=False, verbose=False, request_timeout=30):
    if verbose and logger.level >= 20:
        logger.setLevel(logging.INFO)

    api = mastodon.Mastodon(api_base_url=api_base, access_token=access_token,
                            request_timeout=request_timeout, ratelimit_method="pace", user_agent=USER_AGENT)

    if queried_hashtag[0] == "#":
        logger.warning(f"Leading '#' was removed from queried hashtag.")
        queried_hashtag = queried_hashtag[1:]

    if (not isinstance(min_id, datetime)):
        min_id = int(min_id)

    queried_toots = []
    try:
        new_toots = api.timeline_hashtag(
            hashtag=queried_hashtag, limit=40, local=local_only, min_id=min_id)
        queried_toots.extend(add_queried_at(new_toots))
    except mastodon.MastodonAPIError as e:
        logger.warning(
            f"There was a problem connecting to {api_base}: {e.args[1:]}")
        return queried_toots
    except mastodon.MastodonNetworkError as e:
        logger.warning(
            f"There was a problem connecting to {api_base}: {e.args[1:]}")
        return queried_toots
    except ConnectTimeout:
        logger.warning(
            f"There was a problem connecting to {api_base}: ConnectTimeout")
        return queried_toots

    if len(queried_toots) == 0:
        logger.info(f"No toots with that hashtag found")
        if verbose and logger.level >= 20:
            logger.setLevel(logging.WARNING)
        return None

    if len(new_toots) >= 40:  # check if this makes sense
        paginate = True
    else:
        paginate = False
    while paginate:
        try:
            new_toots = api.fetch_previous(new_toots)
            if len(new_toots) > 0:
                queried_toots.extend(add_queried_at(new_toots))
                logger.info(
                    f"Got {len(queried_toots)} toots from {api_base} ({api.ratelimit_remaining} calls remaining, reset at {datetime.fromtimestamp(api.ratelimit_reset):%Y-%m-%d %H:%M:%S})")
                if max_id and any([t["id"] > max_id for t in new_toots]):
                    paginate = False
            else:
                paginate = False
        except:
            return queried_toots

    logger.handlers[0].flush()
    if verbose and logger.level >= 20:
        logger.setLevel(logging.WARNING)

    return queried_toots


class Sampler(mastodon.StreamListener):
    def __init__(self, file_name="toots", filter_string=None):
        self.n_toots = 0
        self.filter_string = filter_string
        self.file_name = file_name

    def on_update(self, status):
        status["queried_at"] = datetime.now()
        self.n_toots += 1
        with open(f"{self.file_name}", "a") as f:
            f.write(json.dumps(status, default=str))
            f.write("\n")

    def on_status_update(self, status):
        status["queried_at"] = datetime.now()
        self.n_toots += 1
        with open(f"{self.file_name}", "a") as f:
            f.write(json.dumps(status, default=str))
            f.write("\n")


def stream_timeline(api_bases, access_token=None, max_toots=None, timeframe=None, filter_string=None, dir_name=None, verbose=False):

    if verbose and logger.level >= 20:
        logger.setLevel(logging.INFO)

    start_time = int(time.time())
    time_passed = int(time.time()) - start_time

    streams = []
    try:
        for api_base in api_bases:
            print(api_base)
            api = mastodon.Mastodon(
                api_base_url=api_base, access_token=access_token, user_agent=USER_AGENT)
            stream_listener = Sampler(file_name=f"{dir_name}/{api_base}.json")
            streams.append((api_base, api.stream_public(listener=stream_listener, run_async=True,
                           reconnect_async=True, reconnect_async_wait_sec=30), stream_listener))
        while time_passed < timeframe:
            time_passed = int(time.time()) - start_time
            for api_base, handler, listener in streams:
                print(f"{api_base : <22}{listener.n_toots}")
            print(f"{timeframe - time_passed} seconds to go")
            time.sleep(60*5)

    except Exception as e:
        print("Error")
        print(e)
    finally:
        for api_base, handler, listener in streams:
            handler.close()

    if verbose and logger.level >= 20:
        logger.setLevel(logging.WARNING)

    # return stream_listener.toots


def get_instances(sort_by="active_users", min_active_users=None, min_users=None, count=5, language=None):
    payload = {
        "count": count,
        "sort_order": "desc",
        "sort_by": sort_by,
        "min_active_users": min_active_users,
        "min_users": min_users,
        "language": language
    }
    r = requests.get("https://instances.social/api/1.0/instances/list", params=payload,
                     headers={"Authorization": f"Bearer {config['INSTANCES.SOCIAL']['api_key']}"})

    if r.status_code == 200:
        return (r.json()["instances"])
    else:
        None
