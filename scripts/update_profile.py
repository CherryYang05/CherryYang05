#!/usr/bin/env python3
"""Render repository-owned GitHub widgets from public data; no image service."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
QUERY = '''query { user(login:"CherryYang05") { login repositories(first:100,ownerAffiliations:OWNER,privacy:PUBLIC) { pageInfo { hasNextPage } nodes { name stargazerCount isFork languages(first:5,orderBy:{field:SIZE,direction:DESC}) { edges { size node { name color } } } } } contributionsCollection { totalCommitContributions totalPullRequestContributions totalIssueContributions totalPullRequestReviewContributions contributionCalendar { totalContributions weeks { contributionDays { date contributionCount color weekday } } } } } }'''

def text(value,x,y,size=16,color='#E9EEFF',weight=None):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}"'+(f' font-weight="{weight}"' if weight else '')+f'>{escape(str(value))}</text>'

def save(name,w,h,body,title):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="title"><title id="title">{escape(title)}</title><rect width="{w}" height="{h}" rx="16" fill="#111931"/><g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif">{body}</g></svg>'
    ET.fromstring(svg)
    (ROOT/'assets/generated'/name).write_text(svg)

def render(data):
    u=data['data']['user'];c=u['contributionsCollection'];cal=c['contributionCalendar'];repos=u['repositories']['nodes']
    if u['repositories'].get('pageInfo',{}).get('hasNextPage'):
        raise RuntimeError('Repository query needs pagination before accurate totals can be rendered.')
    stamp=datetime.now(timezone.utc).strftime('%Y-%m-%d')
    days=[d for w in cal['weeks'] for d in w['contributionDays']]
    months=defaultdict(int)
    for day in days:months[day['date'][:7]]+=day['contributionCount']
    months=sorted(months.items())[-12:]
    # Metrics have explicit scopes; calendar totals are not labelled as commits.
    for mobile in [False,True]:
        w,h=(360,314) if mobile else (960,268)
        body=text('A year in code',24 if mobile else 32,40,25,weight=600)
        body+=text(f'Updated {stamp}',24 if mobile else 766,65 if mobile else 38,12,'#ACBBDC')
        metrics=[(cal['totalContributions'],'contributions'),(c['totalCommitContributions'],'commits'),(c['totalPullRequestContributions'],'pull requests')]
        for i,(value,label) in enumerate(metrics):
            x=(16+i*115) if mobile else (32+i*157)
            body+=text(value,x,112 if mobile else 94,31,weight=600)+text(label,x,137 if mobile else 118,14,'#BAC6E4')
        startx,starty=(24,172) if mobile else (530,64)
        chartw,charth=(312,94) if mobile else (395,128)
        maxval=max([v for _,v in months]+[1]);step=chartw/max(len(months),1)
        body+=f'<path d="M{startx} {starty+charth}H{startx+chartw}" stroke="#405176"/>'
        for i,(month,value) in enumerate(months):
            bh=max(2,value/maxval*charth);x=startx+i*step+2;y=starty+charth-bh
            body+=f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(2,step-9):.1f}" height="{bh:.1f}" rx="3" fill="'+('#F4B8CF' if i==len(months)-1 else '#879BFF')+'"><title>'+escape(month)+f': {value} contributions</title></rect>'
            if i%2==0:body+=text(month[5:],round(x),starty+charth+19,13,'#BAC6E4')
        if mobile:
            body+=text('Monthly contributions · last 12 months',24,301,13,'#ACBBDC')
        else:
            stars=sum(r['stargazerCount'] for r in repos if not r['isFork'])
            body+=text(f'{len(repos)} public repos  /  {stars} stars on non-fork repos',33,169,14,'#BAC6E4')
            body+=text('Monthly contributions · last 12 months',530,231,13,'#ACBBDC')
            body+=text('Small changes, over time.',33,229,17,'#D6DFFF')
        save('activity-mobile.svg' if mobile else 'activity.svg',w,h,body,f"GitHub activity: {cal['totalContributions']} contributions in the last year. Updated {stamp}.")
    # Language byte counts are code composition across public non-fork repos,
    # never a score for proficiency. Only the top languages per repo are sampled.
    totals=defaultdict(int);colors={}
    for repo in repos:
        if repo['isFork']:continue
        for edge in repo['languages']['edges']:
            name=edge['node']['name'];totals[name]+=edge['size'];colors[name]=edge['node']['color'] or '#879BFF'
    ranked=sorted(totals.items(),key=lambda item:item[1],reverse=True)[:5]
    total=sum(value for _,value in ranked) or 1
    body=text('Languages in my repos',25,35,23,weight=600)
    x=26
    for name,value in ranked:
        width=396*value/total
        body+=f'<rect x="{x:.1f}" y="56" width="{width:.1f}" height="11" fill="{colors[name]}"/>';x+=width
    for i,(name,value) in enumerate(ranked):
        y=97+i*23
        body+=f'<circle cx="31" cy="{y-5}" r="4" fill="{colors[name]}"/>'+text(name,43,y,17)+text(f'{value/total:.1%}',365,y,16,'#BAC6E4')
    body+=text('Sampled bytes · public non-fork repos',25,222,14,'#ACBBDC')
    save('languages.svg',450,240,body,'Code languages by sampled bytes in public non-fork repositories, not proficiency.')
    (ROOT/'assets/generated/snapshot.json').write_text(json.dumps({'updated':stamp,'scope':'Public GitHub repositories; non-fork language sample; GitHub contribution calendar','contributions_last_year':cal['totalContributions'],'commits_last_year':c['totalCommitContributions'],'pull_requests_last_year':c['totalPullRequestContributions'],'monthly':dict(months),'language_bytes':dict(ranked)},indent=2)+'\n')
    print('Rendered activity and language widgets from public GitHub data.')

def readme(revision):
    if not re.fullmatch(r'[0-9a-f]{40}',revision):raise ValueError('Asset revision must be an immutable 40-character commit SHA.')
    path=ROOT/'README.md';value=path.read_text()
    # Only generated image URLs change; static design revisions stay pinned.
    value=re.sub(r'cdn\.jsdelivr\.net/gh/CherryYang05/CherryYang05@[0-9a-f]{40}/assets/generated/',f'cdn.jsdelivr.net/gh/CherryYang05/CherryYang05@{revision}/assets/generated/',value)
    path.write_text(value)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path);parser.add_argument('--readme-revision');args=parser.parse_args()
    if args.readme_revision:readme(args.readme_revision)
    else:
        if args.data:data=json.loads(args.data.read_text())
        else:
            token=os.environ['GH_TOKEN']
            req=urllib.request.Request('https://api.github.com/graphql',data=json.dumps({'query':QUERY}).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','User-Agent':'CherryYang05-profile-widgets'})
            with urllib.request.urlopen(req,timeout=40) as result:data=json.load(result)
        if data.get('errors'):raise RuntimeError('GitHub query failed; keeping existing widgets: '+json.dumps(data['errors']))
        render(data)
