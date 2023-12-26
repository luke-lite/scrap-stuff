from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup

# from funcs import create_game_info, create_team_info, create_info_df, create_boxscores, merge_boxscores, change_dtypes, create_PIE, commit_data

import pandas as pd
import numpy as np
import string
import time
import sqlite3
import warnings
warnings.filterwarnings('ignore')

pd.set_option('display.max_columns', None)

options = Options()
options.page_load_strategy='eager'
svc=Service(ChromeDriverManager().install())

def create_boxscores(table, game_id):

    # ignore first 'tr', it is table title, not column
    rows = table.findAll('tr')[1:]
    # first 'th' is 'Starters', but will be changed into the player names
    headers = rows[0].findAll('th')
    # provide column names
    headerlist = [h.text.strip() for h in headers]
    
    # ignore first row (headers)
    data = rows[1:]
    # get names column
    player_names = [row.find('th').text.strip() for row in rows]
    # get player stats
    player_stats = [[stat.text.strip() for stat in row.findAll('td')] for row in data]
    # add player name as first entry in each row
    for i in range(len(player_stats)):
        # ignore header with i+1
        player_stats[i].insert(0, player_names[i+1])
    
    # create player stats dataframe
    player_box_df = pd.DataFrame(player_stats, columns=headerlist)
    # drop 'Reserves' row
    player_box_df.drop(player_box_df[player_box_df['Starters'] == 'Reserves'].index, inplace=True)
    
    # add game id column
    player_box_df.insert(loc=0, column='game_id', value=game_id)
    
    # create team stats dataframe from last row in player stats
    team_box_df = pd.DataFrame(player_box_df.iloc[-1]).T
    
    #drop team totals from player stats df
    player_box_df = player_box_df[:-1].rename(columns={'Starters': 'player'})

    return player_box_df, team_box_df

def merge_boxscores(boxscore_list, team_ids, scope):

    # create tuple for every 2 boxscores in list
    pairs = [((boxscore_list[i]), (boxscore_list[i + 1])) for i in range(0, len(boxscore_list), 2)]
    
    clean_boxscores= []
    
    for pair in pairs:
        
        # combine regular and adv boxscores
        df = pd.concat([*pair], axis=1)
        # drop columns with duplicate names
        df = df.loc[:,~df.columns.duplicated()].copy()
        
        clean_boxscores.append(df)
    
    for i in range(len(clean_boxscores)):
        
        if scope=='team':
            clean_boxscores[i].rename(columns={'Starters': 'team'}, inplace=True)
            clean_boxscores[i]['team'] = team_ids[i]
            
        elif scope=='player':
            clean_boxscores[i].insert(loc=2, column='team', value=team_ids[i])
    
    return clean_boxscores

def change_dtypes(df, num_columns):

    df.replace(to_replace='', value='-99', inplace=True)
    
    for column in num_columns[1:]:
        df[column] = df[column].astype('float64')
        
    df.replace(to_replace=-99, value=np.nan, inplace=True)
    
    return df

def create_PIE(player_boxes, totals):
    
    PIE_denom = (totals['PTS'] + totals['FG'] + totals['FT'] - totals['FGA'] - totals['FTA'] + totals['DRB'] + (0.5*totals['ORB']) + totals['AST'] + totals['STL'] + (0.5*totals['BLK']) - totals['PF'] - totals['TOV'])
    player_boxes['PIE'] = round((100 * (player_boxes['PTS'] + player_boxes['FG'] + player_boxes['FT'] - player_boxes['FGA'] - player_boxes['FTA'] + player_boxes['DRB'] + (0.5*player_boxes['ORB']) + player_boxes['AST'] + player_boxes['STL'] + (0.5*player_boxes['BLK']) - player_boxes['PF'] - player_boxes['TOV']) / PIE_denom), 1)
    
    return player_boxes

def commit_data(url_list):
    for i in range(len(url_list)):

        driver.get(url_list[i])
        delay
        src = driver.page_source
        parser = BeautifulSoup(src, 'lxml')

        # game_info database:

        id_table = parser.find('table', attrs = {'class': 'suppress_all stats_table', 'id': 'line_score'})
        game_info = create_game_info(url=url_list[i],
                                     season_id=season_id,
                                     season_gamecount=season_gamecount)
        # will use game_id with create_boxscores()
        game_id = game_info[0]
        team_info = create_team_info(id_table)
        # will use team_ids with merge_boxscores()
        team_ids = [team_info[0], team_info[2]]

        info_df = create_info_df(game_info=game_info,
                                 team_info=team_info,
                                 info_columns=info_columns)
        # write game info to sql database
        info_df.to_sql('game_info', con=conn, if_exists='append', index=False)

        # team/player databases:

        # 4 boxscore tables : away_box, away_box_adv, home_box, home_box_adv
        stat_tables = parser.findAll('table', attrs = {'class': 'sortable stats_table now_sortable'})

        player_box_list = [None, None, None, None]
        team_box_list = [None, None, None, None]

        # create team and player boxscores
        for i in range(len(stat_tables)):
            # split player and team boxscores
            player_box_list[i], team_box_list[i] = create_boxscores(stat_tables[i], game_id=game_id)

        # team_stats database:

        # combine boxscore and advanced boxscore for each team
        away_team_box, home_team_box = merge_boxscores(team_box_list, team_ids=team_ids, scope='team')
        team_boxes = pd.concat([away_team_box, home_team_box])
        team_boxes.reset_index(drop=True, inplace=True)
        # prepare numeric data
        team_boxes = change_dtypes(team_boxes, num_columns)
        # write to sql database
        team_boxes.to_sql('team_stats', con=conn, if_exists='append', index=False)

        # player_stats database:

        # combine boxscore and advanced boxscore for each team
        away_player_box, home_player_box = merge_boxscores(player_box_list, team_ids=team_ids, scope='player')
        player_boxes = pd.concat([away_player_box, home_player_box])
        player_boxes.reset_index(drop=True, inplace=True)
        # prepare numeric data
        player_boxes = change_dtypes(player_boxes, num_columns)
        # create team totals for PIE calculation
        totals = dict(team_boxes.loc[:,'FG':'PTS'].sum())
        # add PIE column to player boxscore
        player_boxes = create_PIE(player_boxes, totals)
        # write to sql database
        player_boxes.to_sql('player_stats', con=conn, if_exists='append', index=False)

        # increase gamecount to create next game_id
        season_gamecount += 1