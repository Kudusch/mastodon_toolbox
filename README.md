# mastodon-toolbox

This collection of software is meant to facilitate the gathering and analysis of data from the Mastodon network. 

- Display server rules in a convenient manner 
- Respect profile/account hashtags like #nosearch, #nobots or #noindex
- Use only the data you need

# Installation

```git clone https://github.com/Kudusch/mastodon_toolbox
cd mastodon_toolbox
virtualenv -p python3 venv
source venv/bin/activate
python -m pip install .
```

Add API keys to `config_example.ini` and rename to `config.ini`

# Data gathering

## Chose relevant instances by analysis of followers 

`mtb instances --users user.txt`

`mtb instances --sort_by active_users --min_active_users 0 --min_users 0 --count 5 --language "de"`

## Continuously gather toots that contain a hashtag

`mtb hashtag --tag=[hashtag] --instances=[instances] --data_dir=[data_dir] --start_date=[start_date]`

## Continuously gather (filtered) public toots

`mtb public --instances=[instances] --data_dir=[data_dir] --start_date=[start_date]`

`mtb public --instances=[instances] --data_dir=[data_dir] --start_date=[start_date] --filter=[filter.txt]`

## Sample public toots

`mtb sample --instances=[instances] --data_dir=[data_dir] --start_date=[start_date] --end_date=[end_date] --size=[size]`

## Gather interactions with toots

`mtb interactions --toots=[toots.txt]`

## Export data

`mtb export --data_dir=[data_dir] --format=csv`
