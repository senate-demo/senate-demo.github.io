year_min = 1969
year_max = 2018
years = range(year_min, year_max + 1)

import json

states = (
    'AK','AL','AR','AZ','CA','CO','CT','DE','FL','GA',
    'HI','IA','ID','IL','IN','KS','KY','LA','MA','MD',
    'ME','MI','MN','MO','MS','MT','NC','ND','NE','NH',
    'NJ','NM','NV','NY','OH','OK','OR','PA','RI','SC',
    'SD','TN','TX','UT','VA','VT','WA','WI','WV','WY'
)

f = open('source.txt','r')
lines = f.readlines()
f.close()

data = []
for line in lines:
    year = int(line[:4])
    state = line[4:6]
    pop = int(line[18:26])
    data.append([year,state,pop])

pops = {}
for year in years:
    pops[year] = {}
    for state in states:
        pops[year][state] = 0

print(pops)
print('about to add')
for line in data:
    if line[1] in states:
        pops[line[0]][line[1]] += line[2]

for year in years:
    for state in state:
        try:
            pops[year][state] = round(pops[year][state] / 100000) / 10
        except KeyError:
            print(pops)
            print(year)
            print(state)

with open('populations.json','w') as f:
    f.write(json.dumps(pops))

print(pops)