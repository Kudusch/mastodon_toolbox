# mastodon-toolbox

This collection of software is meant to facilitate the gathering and analysis of data from the Mastodon network. 

- Display server rules in a convenient manner 
- Respect profile/account hashtags like #nosearch, #nobots or #noindex
- Use only the data you need

# Installation

`git clone https://github.com/Kudusch/mastodon_toolbox`
`virtualenv -p python3 venv && source venv/bin/activate`
`pip install -r requirements.txt`

# Data gathering

## Chose relevant instances by analysis of followers 

`mastodon-tb instances --users user.txt`
`mastodon-tb instances --sort_by active_users --min_active_users 0 --min_users 0 --count 5 --language "de"`

## Continuously gather toots that contain a hashtag

`mastodon-tb hashtag --tag=[hashtag] --instances=[instances] --data_dir=[data_dir] --start_date=[start_date]`

## Continuously gather (filtered) public toots

`mastodon-tb public --instances=[instances] --data_dir=[data_dir] --start_date=[start_date]`

`mastodon-tb public --instances=[instances] --data_dir=[data_dir] --start_date=[start_date] --filter=[filter.txt]`

## Sample public toots

`mastodon-tb sample --instances=[instances] --data_dir=[data_dir] --start_date=[start_date] --end_date=[end_date] --size=[size]`

## Gather interactions with toots

`mastodon-tb interactions --toots=[toots.txt]`

## Export data

`mastodon-tb export --data_dir=[data_dir] --format=csv`