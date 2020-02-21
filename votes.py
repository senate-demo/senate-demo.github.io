import os
from lxml import etree
import re
import json
from urllib.request import urlopen, Request

state_codes = [
    'AK','AL','AR','AZ','CA','CO','CT','DE','FL','GA',
    'HI','IA','ID','IL','IN','KS','KY','LA','MA','MD',
    'ME','MI','MN','MO','MS','MT','NC','ND','NE','NH',
    'NJ','NM','NV','NY','OH','OK','OR','PA','RI','SC',
    'SD','TN','TX','UT','VA','VT','WA','WI','WV','WY'
]

def generate_js(vote, year, vote_number):
    js = "let raw_vote = '%s'" % vote
    path = 'data/%d/' % year
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path))
    name = '%d.js' % vote_number
    with open(path + name,'w') as f:
        f.write(js)

def add_metadata(vote_metadata, year, vote_number):
    year = str(year)
    vote_number = str(vote_number)
    f = open('index/data.json','r')
    index = json.loads(f.read())
    f.close()

    if index.get(year) == None:
        index[year] = {}

    index[year][vote_number] = vote_metadata

    with open('index/data.json','w') as f:
        f.write(json.dumps(index))

    js = "let year_index = '%s'" % json.dumps(index[year])
    with open('index/sources/%s.js' % year,'w') as f:
        f.write(js)

# all requests start with this url
base_url = 'https://www.senate.gov/legislative/LIS/'

def download_xml(url):
    
    user_agent = 'Mozilla/5.0'
    headers = {'User-Agent': user_agent} 
    response = urlopen(Request(url,headers=headers)) 
    xml = response.read()

    return xml

def get_congress_session(year):

    # get which congress it was (eg 116th congress for 2020)
    congress = year + (year % 2)
    congress -= 1788
    congress /= 2
    congress = int(congress)

    # get session number (1 for odd years, 2 for even years)
    session = 1 if year % 2 else 2

    return congress, session

def download_votes(year):
    
    # download index of votes
    congress, session = get_congress_session(year)
    url = base_url + 'roll_call_lists/vote_menu_%d_%d.xml' % (congress, session)
    xml = download_xml(url)
    xml = etree.fromstring(xml)
    
    # validate page
    valid_page = not 'Requested Page Not Found (404)' in str(xml)
    legit_congress = congress == int(xml.xpath('congress')[0].text)
    legit_year = year == int(xml.xpath('congress_year')[0].text)
    if not (valid_page and legit_congress and legit_year):
        print('could not find valid index page at %s' % url)
        return None
    
    # make dir for year
    if not os.path.exists('cache/%d' % year):
        os.makedirs(os.path.dirname('cache/%d/' % year))
    
    # download votes from index
    for item in xml.xpath('//vote'):
        vote_number = int(item.xpath('vote_number')[0].text)
        url = base_url + 'roll_call_votes/vote%d%d/vote_%d_%d_%05d.xml'
        url = url % (congress, session, congress, session, vote_number)
        xml = download_xml(url)
        with open('cache/%d/%d.xml' % (year, vote_number),'wb') as f:
            f.write(xml)
        print('(%d) downloaded vote #%d' % (year, vote_number))


def parse_vote(year, vote_number):

    ########################
    # setup
    ########################
    
    # load xml
    congress, session = get_congress_session(year)
    f = open('cache/%d/%d.xml' % (year, vote_number),'r')
    xml = f.read()
    xml = etree.XML(xml.encode('utf-8'))
    f.close()
    
    # these votes don't matter
    if 'This vote was vacated' in str(xml):
        return

    # shortcut to extract data from xml
    def page_val(key, source=xml):
        page_string = str(source.xpath('string(%s)' % key))

        page_string = page_string.replace('"','&quot')
        page_string = page_string.replace('\'','&apos')
        return page_string
    
    # number of millions, rounded to the 100,000 place
    def shorten(population):
        return round(population / 100000) / 10
    
    # get population data 
    f = open('population/populations.json','r')
    populations = json.loads(f.read())
    f.close()
    state_pops = populations[str(year if year < 2019 else 2018)]
    national_pop = sum(state_pops.values())
    
    # if vote choices 'yay'/'nay' or 'guilty'/'not guilty'
    vote_choices = ['Yea', 'Nay'] 
    if 'Guilty or Not Guilty' in page_val('vote_question_text'):
        vote_choices = ['Guilty', 'Not Guilty']

    ########################
    # vote details
    ########################

    # senate.gov link to vote
    vote_url = base_url + 'roll_call_lists/roll_call_vote_cfm.cfm'
    vote_url += '?congress=%d&session=%d&vote=%05d'
    vote_url = vote_url % (congress, session, vote_number)
    link = '<a target=_blank href=%s>View on senate.gov</a>' % vote_url

    # str for when it happened, eg 'Congress 116, Session 2 — February 5, 2020'
    date = page_val('vote_date')
    date = ','.join(date.split(',')[:-1])
    session_msg = 'Congress %d, Session %d — %s' % (congress, session, date)

    # details for header card on page
    details = {
        'title': page_val('vote_title'),
        'details': session_msg,
        'subject': page_val('vote_document_text'),
        'result': page_val('vote_result_text'),
        'link': link,
    }

    ########################
    # disclaimers
    ########################

    disclaimers = []

    # build description for senators who did not vote
    non_voters = 0
    for category in ('present','absent'):
        count = page_val('count/%s' % category)
        count = int(count) if count else 0
        non_voters += count
    if non_voters > 0:
        plural = 's' if non_voters > 1 else ''
        pres_abs_msg = '%d Senator%s did not vote. See the state list below.'
        pres_abs_msg = pres_abs_msg % (non_voters, plural)
        disclaimers.append(pres_abs_msg)

    # check for tie-breaker
    tie_breaker_vote = page_val('tie_breaker/tie_breaker_vote')
    if tie_breaker_vote:
        tie_breaker = page_val('tie_breaker/by_whom')
        tie_breaker_msg = 'This count includes a %s tie-breaking vote of "%s"'
        tie_breaker_msg = tie_breaker_msg % (tie_breaker, tie_breaker_vote)
        disclaimers.append(tie_breaker_msg)

    ########################
    # states object
    ########################

    # build initial object
    states = {}
    for state in state_codes:
        pop = state_pops[state]
        score = round((2 * national_pop) / pop)
        states[state] = {
            'pop': '%s million' % shorten(pop),
            'score': '%d%%' % score,
            'senators': []
        }

    # add senator data
    for member in xml.xpath('members/member'):

        first_name = page_val('first_name', member) 
        last_name = page_val('last_name', member)
        full_name = ' '.join([first_name, last_name])
        choice = page_val('vote_cast', member)
        party = page_val('party', member)

        senator = {
            'name': full_name,
            'party': party,
            'choice': choice
        }
        
        state = page_val('state', member)
        states[state]['senators'].append(senator)

    ########################
    # get representation data
    ########################

    stats = {
        'votes': {
            'senators': {
                vote_choices[0]: int(page_val('count/yeas') or 0),
                vote_choices[1]: int(page_val('count/nays') or 0)
            },
            'pop': {
                vote_choices[0]: 0,
                vote_choices[1]: 0
            }
        },
        'parties': {
            'senators': {
                'R': 0,
                'D': 0,
                'O': 0
            },
            'pop': {
                'R': 0,
                'D': 0,
                'O': 0
            }
        }
    }

    # get vote + party distributions
    for state_code in state_codes:
        represents_pop = state_pops[state_code] / 2
        for senator in states[state_code]['senators']:
            party = senator['party']
            choice = senator['choice']
            if choice in vote_choices:
                stats['votes']['pop'][choice] += represents_pop
            if not party in ['R', 'D']:
                party = 'O'
            stats['parties']['senators'][party] += 1
            stats['parties']['pop'][party] += represents_pop

    ########################
    # format representation data
    ########################

    # generate string for population stat like '34.2% (192.4 million)'
    def stat_desc(segment_pop):
        pop_percentage = round(100 * segment_pop / national_pop, 1)
        pop_formatted = shorten(segment_pop)
        msg = '%s%% (%s million)' % (pop_percentage, pop_formatted)
        return msg

    # stats msgs for display
    stats_msgs = {
        'votes': {
            'senators': [],
            'pop': []
        },
        'parties': {
            'senators': [],
            'pop': []
        }
    }

    # for vote stats
    total_votes = sum(stats['votes']['senators'].values())
    for choice in vote_choices:

        # senators
        vote_count = stats['votes']['senators'][choice]
        vote_proportion = round(100 * vote_count / total_votes, 1)
        msg = '%s: %d (%s%%)' % (choice, vote_count, vote_proportion)
        stats_msgs['votes']['senators'].append(msg)

        # population
        msg = 'Citizens represented by Senators who voted <i>%s</i>: %s'
        msg = msg % (choice, stat_desc(stats['votes']['pop'][choice]))
        stats_msgs['votes']['pop'].append(msg)

    # for party stats
    for party in ('R', 'D', 'O'):

        parties = {
            'R':'Republican',
            'D':'Democratic',
            'O':'Independent/Other'
        }

        # senators
        msg = '%d%% %s' % (stats['parties']['senators'][party], parties[party])
        stats_msgs['parties']['senators'].append(msg)

        # population
        msg = 'Citizens represented by %s Senators: %s'
        msg = msg % (parties[party], stat_desc(stats['parties']['pop'][party]))
        stats_msgs['parties']['pop'].append(msg)

    ########################
    # output data
    ########################

    # build vote object
    vote = {
        'details': details,
        'disclaimers': disclaimers,
        'states': states,
        'stats_msgs': stats_msgs,
        'stats': stats,
    }

    vote_text = json.dumps(vote)
    generate_js(vote_text, year, vote_number)

    vote_metadata = {
        'title': vote['details']['title'],
        'details': vote['details']['details'],
        'subject': vote['details']['subject'],
        'link': 'year=%d&vote=%d' % (year, vote_number)
    }

    add_metadata(vote_metadata, year, vote_number)

    print('vote %d-%d updated' % (year, vote_number))

def update_year(year):
    votes = os.listdir('cache/%d' % year)
    votes = list(map(lambda v: int(v.split('.')[0]), votes))
    votes.sort()
    for vote in votes:
        parse_vote(year, vote)

def update_all():
    for year in os.listdir('cache'):
        update_year(int(year))
update_all()