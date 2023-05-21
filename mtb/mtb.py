import argparse
import csv
import json
import sys
from os import path, listdir
from shutil import rmtree
from datetime import datetime
from collections import Counter
from statistics import mean
import logging
from . import functions as mf

logger = logging.getLogger("mastodon_functions")

def run_cleanup(args):
    rmtree("build")
    rmtree("mtb.egg-info")

def run_instances(args):
    if args.user_urls:
        user_urls = [user.strip() for user in args.user_urls.readlines()]
        print(f"Getting {args.max_followers} followers for {len(user_urls)} accounts")

        all_followers = []
        for account_url in user_urls:
            try:
                followers = mf.get_account_followers(account_url, max_followers = args.max_followers, verbose = False)
                all_followers.extend(followers)
                message = f"Got {len(followers)} followers of {account_url}"
                print(f'{message: <70}', end = "\r")
            except:
                pass

        if args.save_followers:
            writer = csv.writer(args.save_followers, dialect="unix")
            writer.writerow(mf.account_key_names+["src_acct"])
            for follower in mf.accounts_to_lines(all_followers, parse_html = True):
                writer.writerow(follower+[account_url])
            args.save_followers.close()

        message = f"Got {len(set([a['url'] for a in all_followers]))} followers for {len(user_urls)} accounts"
        print(f'{message: <70}', end = "\n\n")
        domains = [mf.acct_to_string(follower).split("@")[1] for follower in all_followers]
        domains = [domain for domain, count in Counter(domains).most_common() if count >= args.min_user_count]
        print(f"These are the most common domains with at least {args.min_user_count} accounts:\n")
        for instance in domains:
            print(instance)

        if args.instances_file:    
            instances = mf.get_instances_by_url(domains, file_name = args.instances_file)
    else:
        print(f"Getting instances that match the following criteria:")
        if args.sort_by:
            print(f"\tsort_by: {args.sort_by}")
        if args.min_active_users:
            print(f"\tin_active_users: {args.min_active_users}")
        if args.min_users:
            print(f"\tmin_users: {args.min_users}")
        if args.count:
            print(f"\tcount: {args.count}")
        if args.language:
            print(f"\tlanguage: {args.language}")
        instances = mf.get_instances(sort_by=args.sort_by, min_active_users=args.min_active_users, min_users=args.min_users, count=args.count, language=args.language)
        if not instances:
            exit("nothing")
        print("\nThese are the instances returned by instances.social:\n")
        for instance in instances:
            print(instance["name"])
        if args.instances_file:
            instances = mf.get_instances_by_url([instance["name"] for instance in instances], file_name = args.instances_file)


def run_hashtag(args):
    if not path.exists(f"{args.data_dir}/search_config.json"):
        if not args.tag:
            print("Please chose a hashtag via --tag", end = "\n")
            exit()
        else:
            hashtag = args.tag.replace("#", "").lower()

        if not args.instances:
            print("Please provide a list of instances via --instances", end = "\n")
            exit()
        else:        
            instances = [i.strip() for i in args.instances.readlines()]
            args.instances.close()
        print(f"Initialising a search on {len(instances)} instances for #{hashtag} in ./{args.data_dir}", end = "\n")
        try:
            min_id = datetime.strptime(args.start_date, "%Y-%m-%d")
            #min_id = (int(round(datetime.strptime(args.start_date, "%Y-%m-%d").timestamp())) * 1000) << 16
            min_ids = dict([(k, min_id) for k in instances])
        except:
            print("For new searches --start_date must be set (YYYY-MM-DD)", end = "\n")
            exit()

        local_only = args.local_only
    else:
        with open(f"{args.data_dir}/search_config.json", "r") as f:
            config_file = json.load(f)
            last_checked = datetime.fromtimestamp(config_file["last_checked"])
            hashtag = config_file["hashtag"]
            instances = config_file["instances"]
            local_only = config_file["local_only"]
            min_ids = config_file["min_ids"]
        print(f"Refreshing timelines from {args.data_dir} on {len(instances)} instances, last checked at {last_checked:%Y-%m-%d %H:%M:%S}", end = "\n")

    timelines = {}
    for instance in instances:
        if instance in mf.access_tokens.keys():
            access_token = mf.access_tokens[instance]
        else:
            access_token = None
        toots = mf.search_hashtag(hashtag, instance, access_token = access_token, local_only = args.local_only,min_id = min_ids[instance], verbose=True)
        timelines[instance] = mf.filter_toots(toots)

    if not all([isinstance(timeline, type(None)) for timeline in timelines.values()]):
        with open(f"{args.data_dir}/{datetime.now().strftime('%s')}_timelines.json", "w") as f:
            json.dump(timelines, f, default=str)

    with open(f"{args.data_dir}/search_config.json", "w") as f:
        for instance in instances:
            if timelines[instance] and len(timelines[instance]) > 0:
                min_ids[instance] = max([t["id"] for t in timelines[instance]])
            elif isinstance(min_ids[instance], datetime):
                min_ids[instance] = (int(round(min_ids[instance].timestamp())) * 1000) << 16
        config = {
            "hashtag":hashtag,
            "instances":instances,
            "local_only":local_only,
            "min_ids":min_ids,
            "last_checked":datetime.now().timestamp()
        }
        json.dump(config, f, default=str)

    uris = []
    for tl in timelines.values():
        if tl:
            uris.extend([t["uri"] for t in tl])
    if uris:
        print(f"\nGot {len(set(uris))} toots from {len(instances)} instances")
    else:
        print(f"\nGot no new toots from {len(instances)} instances")

def run_public(args):
    if not path.exists(f"{args.data_dir}/search_config.json"):
        if not args.instances:
            print("Please provide a list of instances")
            exit()
        else:        
            instances = [i.strip() for i in args.instances.readlines()]
            args.instances.close()
        if args.filter:
            print(f"Initialising a search for '{args.filter}' on {len(instances)} instances in ./{args.data_dir}")
        else:
            print(f"Initialising a search on {len(instances)} instances in ./{args.data_dir}")
        try:
            min_id = datetime.strptime(args.start_date, "%Y-%m-%d")
            #min_id = (int(round(datetime.strptime(args.start_date, "%Y-%m-%d").timestamp())) * 1000) << 16
            min_ids = dict([(k, min_id) for k in instances])
        except:
            print("For new searches --start_date must be set (YYYY-MM-DD)")
            exit()
        local_only = args.local_only
        filter_query = args.filter
    else:
        with open(f"{args.data_dir}/search_config.json", "r") as f:
            config_file = json.load(f)
            filter_query = config_file["filter_query"]
            last_checked = datetime.fromtimestamp(config_file["last_checked"])
            instances = config_file["instances"]
            min_ids = config_file["min_ids"]
            local_only = config_file["local_only"]
        print(f"Refreshing timelines from {args.data_dir} last checked at {last_checked:%Y-%m-%d %H:%M:%S}")

    timelines = {}
    for instance in instances:
        if instance in mf.access_tokens.keys():
            access_token = mf.access_tokens[instance]
        else:
            access_token = None

        toots = mf.search_public(instance, access_token, min_id = min_ids[instance], local_only = args.local_only, verbose=True)
        timelines[instance] = mf.filter_toots(toots, query=filter_query)

    if not all([isinstance(timeline, type(None)) for timeline in timelines.values()]):
        with open(f"{args.data_dir}/{datetime.now().strftime('%s')}_timelines.json", "w") as f:
            json.dump(timelines, f, default=str)

    with open(f"{args.data_dir}/search_config.json", "w") as f:
        for instance in instances:
            if timelines[instance] and len(timelines[instance]) > 0:
                min_ids[instance] = max([t["id"] for t in timelines[instance]])
        config = {
            "filter_query":filter_query,
            "instances":instances,
            "local_only":local_only,
            "min_ids":min_ids,
            "last_checked":datetime.now().timestamp()
        }
        json.dump(config, f)
    
    uris = []
    for tl in timelines.values():
        if tl:
            uris.extend([t["uri"] for t in tl])
    if uris:
        print(f"\nGot {len(set(uris))} toots from {len(instances)} instances")
    else:
        print(f"\nGot no new toots from {len(instances)} instances")

def run_interactions(args):
    def to_rows(interactions):
        for kind, interaction in interactions.items():
            for announcement in interaction.values():
                if kind == "context":
                    ancestors, descendants, source = announcement.values()
                    announcement_list = (ancestors + descendants)
                else:
                    announcement_list, source = announcement.values()
                if source == "deleted" or source == "error":
                    continue
                dest_acct = mf.acct_to_string(source["account"])
                dest_content = mf.parse_toot_html(source["content"])
                
                if kind == "context":
                    for src_post in announcement_list:
                        src_acct = mf.acct_to_string(src_post["account"])
                        src_content = mf.parse_toot_html(src_post["content"])
                        yield [dest_acct, src_acct, kind, dest_content, src_content]
                else:
                    for src_acct in announcement_list:
                        yield [dest_acct, mf.acct_to_string(src_acct), kind, dest_content, ""]
    
    toots = json.load(args.toots)
    args.toots.close()
    print(f"Getting interactions with {len(toots)} toots.")
    reblogs = mf.get_toots_reblogs(toots, verbose=True)
    favourites = mf.get_toots_favourites(toots, verbose=True)
    context = mf.get_toots_context(toots, verbose=True)
    if args.format == "json":
        json.dump({"reblogs":reblogs, "favourites":favourites, "context":context}, args.out_file, default=str)
    elif args.format == "csv":
        writer = csv.writer(args.out_file, dialect="unix")
        writer.writerow(["destination", "source", "kind", "dest_content", "src_content", "tag", "instance"])
        for row in to_rows({"reblogs":reblogs, "favourites":favourites, "context":context}):
            writer.writerow(row)


def run_export(args):
    if path.exists(f"{args.data_dir}/search_config.json"): 
        with open(f"{args.data_dir}/search_config.json", "r") as f:
            config_file = json.load(f)
        timelines = {}
        files = [f for f in listdir(args.data_dir) if not f.startswith(".") and f != "search_config.json" and f.endswith(".json")]
        for fname in files:
            with open(f"{args.data_dir}/{fname}", "r") as f:
                for k, v in json.load(f).items():
                    if v:
                        if k in timelines:
                            timelines[k].extend(v)
                        else:
                            timelines[k] = v
        
        with open(f"{args.out_file}", "w") as out_file:
            if args.format == "json":
                if args.aggregate:
                    toots = []
                    for instance, uri, toot in mf.aggregate_timelines(timelines):
                        toots.append(toot)
                    json.dump(toots, out_file, default=str)
                    print(f"Wrote {len(toots)} unique toots to {out_file.name}")
                else:
                    json.dump(timelines, out_file, default=str)
                    print(f"Wrote toots from {len(timelines.keys())} instances to {out_file.name}")
                
            elif args.format == "csv":
                writer = csv.writer(out_file, dialect="unix")
                writer.writerow(mf.key_names)
                if args.aggregate:
                    n_toots = 0
                    for instance, uri, toot in mf.aggregate_timelines(timelines):
                        toot = mf.toots_to_lines([toot], parse_html = args.parse_html, instance_name = instance, verbose=False)
                        writer.writerow(toot[0])
                        n_toots += 1
                    print(f"Wrote {n_toots} toots from {len(timelines.keys())} instances to {out_file.name}")
                else:
                    for instance, toots in timelines.items():
                        toots = mf.toots_to_lines(toots, parse_html = args.parse_html, instance_name = instance, verbose=False)
                        for toot in toots:
                            writer.writerow(toot)
                    print(f"Wrote toots from {len(timelines.keys())} instances to {out_file.name}")
    else:
        files = [f for f in listdir(args.data_dir) if not f.startswith(".") and f.endswith("_trends.json")]
        all_tags = {}
        all_links = {}
        all_statuses = {}
        for fname in files:
            with open(f"{args.data_dir}/{fname}", "r") as f:
                for instance, trends in json.load(f).items():
                    if not trends:
                        continue
                    if instance in all_tags:
                        all_tags[instance].extend(trends["tags"])
                    else:
                        all_tags[instance] = trends["tags"]
                    if instance in all_links:
                        all_links[instance].extend(trends["links"])
                    else:
                        all_links[instance] = trends["links"]
                    if instance in all_statuses:
                        all_statuses[instance].extend(trends["statuses"])
                    else:
                        all_statuses[instance] = trends["statuses"]
        
        with open(f"tags.csv", "w") as tag_file:
            tag_writer = csv.writer(tag_file, dialect="unix")
            tag_writer.writerow(mf.trends_key_names["tags"] + ["day", "accounts", "uses", "instance"])
            for instance, tags in all_tags.items():
                for tag in tags:
                    for history in tag["history"]:
                        day, accounts, uses = history.values()
                        tag_writer.writerow([tag[k] for k in mf.trends_key_names["tags"]] + [day, accounts, uses, instance])
        
        with open(f"links.csv", "w") as link_file:
            link_writer = csv.writer(link_file, dialect="unix")
            link_writer.writerow(mf.trends_key_names["links"] + ["day", "accounts", "uses", "instance"])
            for instance, links in all_links.items():
                for link in links:
                    for history in link["history"]:
                        day, accounts, uses = history.values()
                        link_writer.writerow([link[k] for k in mf.trends_key_names["links"]] + [day, accounts, uses, instance])
        
        for instance, statuses in all_statuses.items():
            mf.toots_to_csv(statuses, file_name = "statuses.csv", parse_html = args.parse_html, instance_name = instance, append=True, verbose=False)
            
        

def run_sample(args):
    timelines = {}
    if not args.instances:
        print("Please provide a list of instances")
        exit()
    else:        
        instances = [i.strip() for i in args.instances.readlines()]
        args.instances.close()

    if not args.start_date or not args.end_date:
        print("Please provide a list of instances")
        exit()
    else:        
        start_date = args.start_date
        args.end_date
    for instance in instances:
        if instance in mf.access_tokens.keys():
            access_token = mf.access_tokens[instance]
        else:
            access_token = None
        # try:
        timelines[instance] = []
        start_date = args.start_date
        end_date = args.end_date
        max_id = (int(round(start_date.timestamp())) * 1000) << 16

        for date_range in mf.daterange(start_date, end_date, days=args.days_between):
            from_date, to_date = date_range
            chunk = mf.search_public(instance, access_token, max_toots = args.chunk_size, max_id=max_id, verbose=False)
            timelines[instance].extend(mf.filter_toots(chunk, query=args.filter))
            max_id = (int(round(from_date.timestamp())) * 1000) << 16
            logger.setLevel(logging.INFO)
            logger.info(f"Got {len(timelines[instance])} toots from {instance}, last chunk {mf.get_datetime_range(chunk)}")
            logger.setLevel(logging.WARNING)
        # except Exception as e:
        #     print(e)
    if not all([isinstance(timeline, type(None)) for timeline in timelines.values()]):
        with open(f"{args.data_dir}/{datetime.now().strftime('%s')}_timelines.json", "w") as f:
            json.dump(timelines, f, default=str)
            
def run_trends(args):
    trends = {}
    if not args.instances:
        print("Please provide a list of instances")
        exit()
    else:        
        instances = [i.strip() for i in args.instances.readlines()]
        args.instances.close()
    
    for instance in instances:
        if instance in mf.access_tokens.keys():
            access_token = mf.access_tokens[instance]
        else:
            access_token = None
        trends[instance] = mf.get_instance_trends(instance, access_token = access_token, verbose = True)
    
    if not all([isinstance(trends, type(None)) for timeline in trends.values()]):
        with open(f"{args.data_dir}/{datetime.now().strftime('%s')}_trends.json", "w") as f:
            json.dump(trends, f, default=str)
    
def date(s):
    return datetime.strptime(s, "%Y-%m-%d")

def main():
    version = 1.0
    parser = argparse.ArgumentParser(
        prog="mtb",
        description="A tool to gather data from Mastodon",
        usage="mtb [-h] command [options]"
    )

    subparsers = parser.add_subparsers(
        title="commands",
        description="Actions to perform",
        required = True
    )

    parser_instances = subparsers.add_parser("instances", help="Chose relevant instances by analysis of followers")
    parser_instances.add_argument("--user_urls", help="File with urls to user profiles", type=argparse.FileType("r"))
    parser_instances.add_argument("--min_user_count", help="Disregard instances with less than user_count users", default=10, type=int)
    parser_instances.add_argument("--max_followers", help="The maximum number of followers per user profile", default=200, type=int)
    parser_instances.add_argument("--save_followers", help="File to save the gathered follower accounts to", type=argparse.FileType("w"))

    parser_instances.add_argument("--sort_by", help="Order or the requested instances", choices=["name", "uptime", "https_score", "obs_score", "users", "statuses", "connections", "active_users"], default="active_users", type=str)
    parser_instances.add_argument("--min_active_users", help="Minimum number of active users", default=None, type=int)
    parser_instances.add_argument("--min_users", help="Minimum number of users", default=None, type=int)
    parser_instances.add_argument("--count", help="Number of instances returned", default=5, type=int)
    parser_instances.add_argument("--language", help="Languages of the instances", default=None, type=str)

    parser_instances.add_argument("--instances_file", help="File to save instance metadata to", type=str)
    parser_instances.set_defaults(func=run_instances)

    parser_hashtag = subparsers.add_parser("hashtag", help="Continuously gather toots that contain a hashtag")
    parser_hashtag.add_argument("--tag", help="Hashtag to gather", type=str)
    parser_hashtag.add_argument("--instances", help="File with urls to instances", type=argparse.FileType("r"))
    parser_hashtag.add_argument("--data_dir", help="Directory where gathered data is saved", type=str)
    parser_hashtag.add_argument("--start_date", help="Start data gathering at this date (YYYY-MM-DD)", type=date)
    parser_hashtag.add_argument("--local_only", help="Only gather toots local to the queried instances", action="store_true")
    parser_hashtag.set_defaults(func=run_hashtag)

    parser_public = subparsers.add_parser("public", help="Continuously gather (filtered) public toots")
    parser_public.add_argument("--instances", help="File with urls to instances", type=argparse.FileType("r"))
    parser_public.add_argument("--data_dir", help="Directory where gathered data is saved", type=str)
    parser_public.add_argument("--start_date", help="Start data gathering at this date (YYYY-MM-DD)", type=date)
    parser_public.add_argument("--local_only", help="Only gather toots local to the queried instances", action="store_true")
    parser_public.add_argument("--filter", help="String to filter queried toots with", type=str)
    parser_public.set_defaults(func=run_public)

    parser_sample = subparsers.add_parser("sample", help="Sample public toots over a period of time")
    parser_sample.add_argument("--instances", help="File with urls to instances", type=argparse.FileType("r"))
    parser_sample.add_argument("--data_dir", help="Directory where gathered data is saved", type=str)
    parser_sample.add_argument("--start_date", help="Start data gathering at this date (YYYY-MM-DD)", type=date)
    parser_sample.add_argument("--end_date", help="End data gathering at this date (YYYY-MM-DD)", type=date)
    parser_sample.add_argument("--chunk_size", help="Number of toots in chunk", default=100, type=int)
    parser_sample.add_argument("--days_between", default=7, type=int)
    parser_sample.add_argument("--filter", help="String to filter queried toots with", type=str)
    parser_sample.add_argument("--local_only", help="Only gather toots local to the queried instances", action="store_true")
    parser_sample.set_defaults(func=run_sample)

    parser_interactions = subparsers.add_parser("interactions", help="Gather interactions with toots")
    parser_interactions.add_argument("--toots", help="json-file with toots", type=argparse.FileType("r"))
    parser_interactions.add_argument("--out_file", help="File to save interactions in", type=argparse.FileType("w"))
    parser_interactions.add_argument("--format", help="Format of output file", choices=["json", "csv"], default="json", type=str)
    parser_interactions.set_defaults(func=run_interactions)

    parser_trends = subparsers.add_parser("trends", help="Continuously gather trends")
    parser_trends.add_argument("--instances", help="File with urls to instances", type=argparse.FileType("r"))
    parser_trends.add_argument("--data_dir", help="Directory where gathered data is saved", type=str)
    parser_trends.set_defaults(func=run_trends)
    
    parser_export = subparsers.add_parser("export", help="Export data")
    parser_export.add_argument("--data_dir", help="Directory to export data from", type=str)
    parser_export.add_argument("--format", help="Format of the exported file", choices=["json", "csv"], default="csv", type=str)
    parser_export.add_argument("--out_file", help="File to export data to", type=str)
    parser_export.add_argument("--parse_html", help="Convert html in toot content and user notes to clean text", action="store_true")
    parser_export.add_argument("--aggregate", help="Aggregate toots over instances timelines", action="store_true")
    parser_export.set_defaults(func=run_export)
    
    parser_cleanup = subparsers.add_parser("clean", help="Clean a fresh installation")
    parser_cleanup.set_defaults(func=run_cleanup)

    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()