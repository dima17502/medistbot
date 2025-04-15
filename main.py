#!/usr/bin/env python
'''
    Author: Dimetriy Volkov
'''

import schedule
import os
from background import keep_alive
import telebot
import traceback
import signal
import sys
import time
from datetime import datetime,timedelta
from db import init_db, get_user_state,update_user_state,update_user_data, get_available_users, update_users_status
from threading import Thread
from telebot import types
import configparser

init_db()

settings = configparser.ConfigParser()

bot = telebot.TeleBot('6481954084:AAHnbj1zyPF6OY5aqdILvllqdlBzbDvplJA', parse_mode='html')

hex_dict = {"a":10,"b":11,"c":12,"d":13,"e":14,"f":15, "10":"a","11":"b","12":"c","13":"d","14":"e","15":"f"}
users = {}
blocked_users = []
user_states = {}
jobs = []
threads = []
interaction = ''
print(user_states)
for i in range(10):
	hex_dict[str(i)] = i
	hex_dict[i] = str(i)
	

def update_error_log(err_mes):
	try:
		with open('error_log.txt', 'a+',encoding="utf-8") as file:
			file.write('-'*20 + str(datetime.now())+ '-'*60 +'\n\n')
			file.write(str(err_mes) + '\n')
	except Exception as err:
		print(err)


def update_db():
	print("from update db at:", str(datetime.now()))
	for u_id in user_states:
		string_path = get_string_path(u_id)
		us = user_states[u_id]
		update_user_state(int(us['current_article']),us['schema_is_open'], us['answers'], string_path, us['last_query'],int(u_id))
	for u_id in users:
		u = users[u_id]
		update_user_data(u['first_name'], u['last_name'], u['username'], int(u_id), int(u['status']))


def clear_log_file():
	open('error_log.txt', 'w').close()

def check_ad():
	settings.read('settings.ini')
	if settings['AD']['should_be_send'] == '1':
		if(settings["AD"]['send_now'] == '1'):
			send_ad()
		else:
			t = Thread(target=delay_send)
			t.start()
			threads.append(t)
		settings.set('AD','send_now','0')
		settings.set('AD','should_be_send', '0')
		with open('settings.ini', 'w') as configfile:
			settings.write(configfile)


def send_ad():
	global blocked_users
	print('from send_ad')
	settings.read('settings.ini')
	av_users = get_available_users()
	caption = 'Реклама помогает этому проекту развиваться. Спасибо за понимание.'
	send_format = settings["AD"]["send_format"]
	if send_format in ("image", "mixed"):
		img_file = open(settings["AD"]["image_path"], 'rb')
	if send_format in ("text","mixed"):
		file = open(settings["AD"]["ad_path"], 'r', encoding="utf-8")
		ad_text = file.read()
		if ad_text.strip():
			caption = ad_text
		file.close()	
	u_id = 0		
	for u in av_users:
		markup = types.ReplyKeyboardMarkup()
		backbtn = types.KeyboardButton('Назад')
		markup.row(backbtn)
		u_id = u[0]
		if True:
			try:
				if send_format == "image":
					with open(settings["AD"]["image_path"], 'rb') as img_file:
						bot.send_photo(u_id, img_file, reply_markup=markup)
				elif send_format == "text":
					bot.send_message(u_id, caption, reply_markup=markup)
				else:
					with open(settings["AD"]["image_path"], 'rb') as img_file:
						bot.send_photo(u_id, img_file, caption, reply_markup=markup)
			except Exception as err:
				print('from exception:', err)
				update_error_log(traceback.format_exc())
				if str(err).find('Error code: 403') != -1:
					blocked_users.append(u_id)
	if len(blocked_users) > 0:
		update_users_status(0,blocked_users)
		for u_id in blocked_users:
			if u_id in users:
				users.pop(u_id, None)
			if u_id in user_states:
				user_states.pop(u_id, None)
			print(user_states, users)
	blocked_users = []

def delay_send():
	settings.read('settings.ini')
	now_msk_time = datetime.utcnow() + timedelta(hours=3)
	send_time = datetime.strptime(settings["AD"]["send_date"], '%d/%m/%y %H:%M:%S')
	sec_delta = (send_time - now_msk_time).total_seconds()
	print(sec_delta)
	if sec_delta < 0:
		return
	while sec_delta > 0:
		time.sleep(1)
		sec_delta -= 1
	else:
		send_ad()

def run_schedules():
	try:
		global jobs
		ad_s = schedule.Scheduler()
		db_s = schedule.Scheduler()
		log_s = schedule.Scheduler()
		jobs = [ad_s,db_s,log_s]
		#ad_s.every().hour.do(check_ad)
		#ad_s.every().day.at("01:41").do(check_ad)
		ad_s.every().minute.at(":00").do(check_ad)
		db_s.every().minute.at(":00").do(update_db)
		#db_s.every().day.at("04:44").do(update_db)				
		log_s.every().day.at("05:06").do(clear_log_file)		
		while True:
			ad_s.run_pending()
			db_s.run_pending()
			log_s.run_pending()
			time.sleep(1)
	except Exception as err_mes:
		update_error_log(traceback.format_exc())

t = Thread(target=run_schedules)
t.start()
threads.append(t)

def signal_handler(sig, frame):
	print('You pressed Ctrl+C!')
	try:
		update_db()
		for s in jobs:
			s.clear()
	except Exception as err:
		update_error_log(traceback.format_exc())
	os._exit(0)
	#sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


def save_user_info(message):
	global users
	users[message.chat.id] = {	'first_name': message.from_user.first_name,
						   		'last_name':message.from_user.last_name,
								'username':message.from_user.username,
								'status':1}


def create_state(user_id):
	lq = ''
	if user_id in user_states and 'last_query' in user_states[user_id]:
		lq = user_states[user_id]['last_query']
	user_states[user_id] = {
		'current_article':'0',
		'data_from_db':1,
		'answers':'',
		'nav_path' :[],
		'schema_is_open':0,
		'from_inline':0,
		'next_func':'',
		'last_query':lq
	}


def import_user_state(user_id):
	res = get_user_state(user_id)
	if res:
		(uid,current_article,schema_is_open,answers,str_path, last_query) = res
		nav_path = []
		if str_path:
			context = nav_dict
			for c in str_path:
				btn_list = list(context)
				if hex_dict[c] <= len(btn_list):
					nav_path.append(btn_list[hex_dict[c] - 1])
					context = context[nav_path[-1]]

		user_states[user_id] = {
			'current_article': str(current_article),
			'data_from_db':1,
			'answers': answers,
			'nav_path': nav_path,
			'schema_is_open': schema_is_open,
			'from_inline':0,
			'next_func': '',
			'last_query': last_query
		}
		res = user_states[user_id]
	return res


@bot.message_handler(commands=['start'])
def start(message):
	try:
		create_state(message.from_user.id)
		save_user_info(message)
		markup = types.ReplyKeyboardMarkup()
		for key in nav_dict:
			btn = types.KeyboardButton(key)
			markup.row(btn)

		bot.send_message(message.chat.id, 'Введите запрос текстом или выберите начать диагностику, чтобы найти симптом, который вас беспокоит',reply_markup=markup)
		user_states[message.chat.id]['next_func'] = 'nav'
	except Exception as err:
		error_at_start(message, traceback.format_exc())


def get_string_path(u_id):
	context = nav_dict
	res = ''
	for s in user_states[u_id]['nav_path']:
		if s in context:
			i = 1
			for j in context:
				if j != s:
					i += 1
				else:
					res += str(hex_dict[str(i)])
					context = context[j]
					break
	return res

def handle_exception(message, err_mes):
	try:
		bot_ans = 'Что-то пошло не так 😔 Давайте попробуем еще раз'
		update_error_log(str(err_mes))
		bot.send_message(message.chat.id,bot_ans)
		start(message)
	except Exception as err:
		error_at_start(message, traceback.format_exc())
		
		
def error_at_start(message,err_mes):
	update_error_log(str(err_mes))


def navigate(message):
	try:
		print('from navigate', user_states)
		markup = types.ReplyKeyboardMarkup()
		nav_path = user_states[message.chat.id]['nav_path']
		age_flag = 0

		if str(message.text).strip()[0].isnumeric():
			user_states[message.chat.id]['last_nav_path'] = tuple(nav_path)
			open_article(message.text, message)
		elif message.text == 'Назад':
			if len(nav_path) != 0:
				if len(nav_path) == 1:
					context = nav_dict
				else:
					context = nav_dict[nav_path[0]]
					for i in range(len(nav_path) - 2):
						context = context[nav_path[i + 1]]
				nav_path.pop()
				cat_flag = 0
				for key in context:
					if  "Подрост" in key or "Дети" in key or "ребен" in key:
						age_flag = 1
					btn = types.KeyboardButton(key)
					markup.row(btn)
				backbtn = types.KeyboardButton("Назад")
				if len(nav_path) > 0:
					markup.row(backbtn)
				botmes = '➡️'*len(nav_path)
				if(botmes == ''):
					botmes = "Введите запрос текстом или выберите начать диагностику, чтобы найти симптом, который вас беспокоит"
				elif age_flag:
					botmes = "Выберите категорию"
				elif len(nav_path) == 1:
					botmes = "Выберите раздел"
				else:
					botmes = "Выберите подраздел"
				bot.send_message(message.chat.id," "+ botmes, reply_markup=markup)
				user_states[message.chat.id]['next_func'] = 'nav'
			else:
				start(message)
		else:
			if len(nav_path) !=0 :
				context = nav_dict[nav_path[0]]
				for i in range(1, len(nav_path)):
					context = context[nav_path[i]]
			else:
				context = nav_dict
			print(nav_dict.keys())
			schema_exists = 0
			if message.text in context:
				nav_path.append(message.text)
				if isinstance(context[message.text],str):
					if context[message.text][:4] == 'http':
						link_text = "<a href='%s'>" % context[message.text] + message.text+"</a>"
						backbtn = types.KeyboardButton("Назад")
						markup.row(backbtn)
						bot.send_message(message.chat.id, link_text, reply_markup=markup)
						user_states[message.chat.id]['next_func'] = 'nav'
					else:
						open_article(context[message.text], message)
				else:
					for key in context[message.text]:
						if (key.strip())[0].isnumeric():
							schema_exists = 1
						elif  "Подрост" in key or "Дети" in key or "ребен" in key:
							age_flag = 1
						btn = types.KeyboardButton(key)
						markup.row(btn)
					backbtn = types.KeyboardButton("Назад")
					markup.row(backbtn)
					botmes = '➡️'*len(nav_path)
					if schema_exists:
						botmes = "Выберите схему"
					elif age_flag:
						botmes = "Выберите категорию"
					elif len(nav_path) == 1:
						botmes = "Выберите раздел"
					else:
						botmes = "Выберите подраздел"
					bot.send_message(message.chat.id, botmes, reply_markup=markup)
					user_states[message.chat.id]['next_func'] = 'nav'
			else:
				user_states[message.chat.id]['next_func'] = ''
				find_symptoms(message, called_from='navigate')
	except Exception as err:
		handle_exception(message, traceback.format_exc())


def back_to_nav(message):

	global schema_nav_dict
	(nav_path,current_article) = (user_states[message.chat.id]['nav_path'],user_states[message.chat.id]['current_article'])
	last_nav_path = tuple(nav_path)
	found = 0
	context = []
	print(last_nav_path)
	if len(last_nav_path) != 0:
		context = nav_dict
		for i in range(len(last_nav_path)):
			context = context[last_nav_path[i]]
		for j in context:
			if current_article in j:
				found = 1
		nav_path = list(last_nav_path)
	if found == 0:
		path = []
		find_chapter(schema_nav_dict,current_article,path, message.chat.id)
		nav_path = list(user_states[message.chat.id]['nav_path'])

		context = schema_nav_dict
		for i in range(len(nav_path)):
			context = context[nav_path[i]]
		nav_path.insert(0, "Начать диагностику ➡️")
		user_states[message.chat.id]['nav_path'] = nav_path
	markup = types.ReplyKeyboardMarkup()

	for key in context.keys():
		btn = types.KeyboardButton(key)
		markup.row(btn)
	btn = types.KeyboardButton("Назад")
	markup.row(btn)
	botmes = '➡️'*len(nav_path)
	user_states[message.chat.id]['current_article'] = '0'	
	bot.send_message(message.chat.id, botmes, reply_markup=markup)
	user_states[message.chat.id]['next_func'] = 'nav'



def find_chapter(context, article, path, user_id):
	for key in context.keys():
		if isinstance(context[key], str) and context[key] == article:
			user_states[user_id]['nav_path'] = tuple(path)
		elif not(isinstance(context[key], str)):
			path.append(key)
			find_chapter(context[key], article, path, user_id)
			path.pop()


def check_art_num(cur_art):
	c = str(cur_art).strip()
	res = 0
	if len(c) > 0 and c[0].isnumeric():
		num = ""
		i = 0
		while i < len(c) and c[i].isnumeric():
			num += c[i]
			i += 1
		num = int(num)
		if num < 148 and num > 0:
			res = str(num)
	return res


def on_click(message):
	try:

		print('from onclick', user_states)
		(current_article, answers, schema_is_open) = (			user_states[message.chat.id]['current_article'],
																user_states[message.chat.id]['answers'],
																user_states[message.chat.id]['schema_is_open'])
		if(check_art_num(current_article)):
			f_path = "./images/" + str(current_article) + '/existing_images.txt'
			with open(f_path, 'r') as file:
				existing_list = file.readlines()
		else:
			existing_list = []
			answers = ''
		if message.text == '/start':
			start(message)
		elif message.text in ("Да", "Нет"):
			if message.text == "Да":
				answers += "y"
			elif message.text == "Нет":
				answers += "n"
			flag = 0
			for f in existing_list:
				if f.rstrip('\n') == (answers+ "y.png"):
					flag = 1
			f_path = './images/' + str(current_article) + '/' + answers +'.png'
			file = open(f_path, 'rb')
			markup = types.ReplyKeyboardMarkup()
			backbtn = types.KeyboardButton('Назад')
			str_article = str(current_article)
			caption = ''
			if str_article in links_dict and answers in links_dict[str_article]: 
				for link in links_dict[str_article][answers]:
					linkbtn = types.KeyboardButton(link)
					markup.row(linkbtn)
			if flag:
				yesbtn = types.KeyboardButton('Да')
				nobtn = types.KeyboardButton('Нет')
				markup.row(yesbtn, nobtn)
			else:
				caption = "<a href='https://t.me/share/url?url=https%3A//t.me/medistBot&text=Бот%2C%20который%20проводит%20диагностику%20по%20симптому%20%F0%9F%8C%A1%E2%9C%A8'>Поделиться ботом💚</a>"
				againBtn = types.KeyboardButton('🔁 Пройти схему заново')
				menuBtn = types.KeyboardButton('🚪 В меню')
				infoBtn = types.KeyboardButton('📖 Полезно знать')
				markup.add(infoBtn)
				markup.add(againBtn, menuBtn)
			markup.row(backbtn)
			user_states[message.chat.id]['answers'] = answers
			bot.send_photo(message.chat.id, file, caption=caption, reply_markup=markup)
			file.close()
			user_states[message.chat.id]['next_func'] = 'on_click'
		elif message.text == "Пройти схему ➡️":			# сделать проверку, что str_article валидный
			user_states[message.chat.id]['schema_is_open'] = 1
			str_article = str(current_article)
			f_path = './images/' + str_article + '/' + str_article + '.png'
			file = open(f_path, 'rb')
			markup = types.ReplyKeyboardMarkup()
			yesbtn = types.KeyboardButton('Да')
			nobtn = types.KeyboardButton('Нет')
			backbtn = types.KeyboardButton('Назад')
			if str_article in links_dict and str_article in links_dict[str_article]:
				for link in links_dict[str_article][str_article]:
					linkbtn = types.KeyboardButton(link)
					markup.row(linkbtn)
			markup.row(yesbtn, nobtn)
			markup.row(backbtn)
			bot.send_photo(message.chat.id, file, reply_markup=markup)
			file.close()
			user_states[message.chat.id]['next_func'] = 'on_click'
		elif message.text in image_dict:
			if len(user_states[message.chat.id]['answers']) == 0 or user_states[message.chat.id]['answers'][-1] != '0':
				user_states[message.chat.id]['answers'] += "0"
			str_article = str(current_article)
			file_name = image_dict[message.text]
			markup = types.ReplyKeyboardMarkup()
			backbtn = types.KeyboardButton('Назад')
			if image_dict[message.text] in links_dict: 
				for link in links_dict[image_dict[message.text]]:
					linkbtn = types.KeyboardButton(link)
					markup.row(linkbtn)
			markup.row(backbtn)
			if file_name[:4] != 'http':
				f_path = './extra_materials'  + '/' + file_name
				files_list = []
				with open('./extra_materials/existing_files.txt', 'r') as file:
					files_list = file.readlines()
				flag = 0
				file_data = ''
				for f in files_list:
					if f.rstrip('\n') == (file_name):
						flag = 1
						if file_name[-4:] == ".txt":
							file = open(f_path, 'r', encoding="utf-8")
							file_data = file.read()
						else:
							file = open(f_path, 'rb')
				# сделать кнопку дополнительно
				if flag:
					if file_name[-4:] == ".txt":
						bot.send_message(message.chat.id, file_data,reply_markup=markup)
					else:
						bot.send_photo(message.chat.id, file, reply_markup=markup)
					file.close()
				else:
					bot.send_message(message.chat.id, "Картинка затерялась, но обязательно найдется позже", reply_markup=markup,parse_mode='html')
			else:
				link_text = "<a href='%s'>" % image_dict[message.text] + message.text+"</a>"
				bot.send_message(message.chat.id, link_text, reply_markup=markup)
			user_states[message.chat.id]['next_func'] = 'on_click'
		elif (str(message.text).strip()[0]).isnumeric():
			num = ""
			str_text = str(message.text).strip()
			i = 0
			while i < len(str_text) and str_text[i].isnumeric():
				num += str_text[i]
				i += 1
			num = int(num)
			if num < 148 and num > 0:
				open_article(num, message)
			else:
				bot.reply_to(message, f'Схемы c таким номером не существует 😔')
				user_states[message.chat.id]['next_func'] = 'on_click'
		elif message.text == 'Назад':
			if str(current_article) != '0' and answers != '':

				f_path = ''
				if len(answers) == 1:
					if answers != '0' or (answers == '0' and schema_is_open):
						user_states[message.chat.id]['answers'] = ''
						message.text = 'Пройти схему ➡️'
						on_click(message)
					else:
						open_article(current_article, message)
				else:
					prev_ans = answers[-2]
					answers = answers[:-2] 
					user_states[message.chat.id]['answers'] = answers
					if prev_ans == 'y':
						message.text = "Да"
					else:
						message.text = "Нет"
					on_click(message)
			elif str(current_article) != '0' and answers == '':
				if(schema_is_open):
					open_article(current_article, message)
				else:
					back_to_nav(message)
		elif message.text == '🚪 В меню':
			user_states[message.chat.id]['nav_path'] = []
			user_states[message.chat.id]['schema_is_open'] = 0
			user_states[message.chat.id]['current_article'] = '0'
			user_states[message.chat.id]['answers'] = ''
			message.text = 'Начать диагностику ➡️'
			navigate(message)
		elif message.text == '🔁 Пройти схему заново':
			if(check_art_num(current_article)):
				f_path = './images/' + str(current_article) + '/' + str(current_article) +'.png'
				file = open(f_path, 'rb')
				markup = types.ReplyKeyboardMarkup()
				yesbtn = types.KeyboardButton('Да')
				nobtn = types.KeyboardButton('Нет')
				markup.row(yesbtn, nobtn)
				user_states[message.chat.id]['answers'] = ''
				bot.send_photo(message.chat.id, file, reply_markup=markup)
				file.close()
				user_states[message.chat.id]['next_func'] = 'on_click'
			else:
				bot.reply_to(message, "Что-то пошло не так 😔. Давайте попробуем заново")
				start(message)
		elif message.text == '📖 Полезно знать':
			markup = types.ReplyKeyboardMarkup()
			backbtn = types.KeyboardButton('Назад')
			markup.row(backbtn)
			current_article = str(current_article)
			art_list = []
			ans_mes = "Вот, что у меня есть:\n"
			for key in links_dict[current_article]:
				for link in links_dict[current_article][key]:
					if link in image_dict and image_dict[link][:4] == "http":
						if link not in art_list:
							art_list.append(link)
							ans_mes += "<a href='%s'>" % image_dict[link] + link+"</a>\n"
			user_states[message.chat.id]['answers'] += '0'
			bot.send_message(message.chat.id, ans_mes, reply_markup=markup,parse_mode="html")
			user_states[message.chat.id]['next_func'] = 'on_click'
		else:
			user_states[message.chat.id]['next_func'] = ''
			find_symptoms(message, called_from='on_click')
			
	except Exception as err:
		handle_exception(message, traceback.format_exc())


warnings = {
	"3":"https://telegra.ph/Silnyj-zhar-09-29",
	"7":"https://telegra.ph/Upornaya-rvota-09-29",
	"14":"https://telegra.ph/Silnyj-zhar-09-29",
	"17":"https://telegra.ph/Dlitelnaya-poterya-soznaniya-09-29",
	"26":"https://telegra.ph/Opasnye-simptomy-09-29",
	"30":"https://telegra.ph/Virusnye-infekcii-i-gluhota-09-30",
	"31":"https://telegra.ph/Opasnye-simptomy-09-30",
	"33":"https://telegra.ph/Opasnye-simptomy-09-30-2",
	"35":"https://telegra.ph/Opasnye-simptomy-09-30-3",
	"37":"https://telegra.ph/Opasnye-simptomy-09-30-4",
	"38":"https://telegra.ph/Opasnye-simptomy-09-30-5",
	"40":"https://telegra.ph/Opasnye-simptomy-09-30-6",
	"41":"https://telegra.ph/Slabitelnye-sredstva-09-30",
	"59":"https://telegra.ph/Povtoryayushchiesya-pristupy-povyshennoj-temperatury-09-30",
	"63":"https://telegra.ph/Dlitelnaya-poterya-soznaniya-10-01",
	"69":"https://telegra.ph/Vyrazhennoe-narushenie-povedeniya-10-01",
	"72":"https://telegra.ph/Samoubijstvo-10-01",
	"73":"https://telegra.ph/Pristupy-paniki-10-01",
	"76":"https://telegra.ph/Izmeneniya-kozhi-10-01",
	"87":"https://telegra.ph/Stojkaya-hripota-10-01",
	"90":"https://telegra.ph/Vyrazhennoe-narushenie-dyhaniya-10-01",
	"93":"https://telegra.ph/Stojkaya-boleznennost-10-01",
	"94":"https://telegra.ph/Krasnaya-ili-chernaya-krov-pri-rvote-10-01",
	"95":"https://telegra.ph/Krasnaya-ili-chernaya-krov-pri-rvote-10-01",
	"96":"https://telegra.ph/Silnaya-bol-v-zhivote-10-01",
	"102":"https://telegra.ph/Krov-v-kale-10-01",
	"104":"https://telegra.ph/Rasstrojstva-mocheispuskaniya-10-27",
	"107":"https://telegra.ph/Postoyannaya-bol-v-spine-10-01",
	"115":"https://telegra.ph/Pripuhlosti-i-otechnost-10-01",
	"116":"https://telegra.ph/Pripuhlosti-i-otechnost-10-01-2",
	"131":"https://telegra.ph/Neproizvolnoe-mocheispuskanie-u-zhenshchin-10-27",
}

schema_nav_dict = {
	'Проблемы младенцев, детей и подростков 👶':
	{
		'Проблемы общего характера 🐹🐶': 
		{
			'Младенцы до года👶':
			{
				'1 - Медленная прибавка в весе ⚖️': '1',
				'2 - Пробуждения по ночам 👀': '2',
				'3 - Высокая температура 🌡': '3',
				'5 - Чрезмерный плач 😿': '5',
				'6 - Трудности кормления 🍽': '6'
			},
			'Дети всех возрастов 👧👦':
			{
				'9 - Плохое самочувствие☹️': '9',
				'10 - Медленный рост ⏲️': '10',
				'11 - Чрезмерная прибавка в весе⚖️': '11',
				'12 - Нарушения сна 😴': '12',
				'13 - Сонливость🥱': '13',
				'14 - Высокая температура 🌡': '14',
				'15 - Опухание желез🐶':'15'
			},
			'Подростки(от 11 до 18 лет) 👩‍🦱🧑‍🦱':
			{
				'50 - Задержка полового созревания ⏱♂️♀️': '50',
				'53 - Нарушения веса ⚖️' : '53'
			}
		},
		'Заболевания кожи, волос и ногтей 👧💅':
		{
			'Младенцы до года 👶':{
				'4 - Кожные нарушения': '4'
			},
			'Дети всех возрастов 👧🏻👦🏻':{
				'16 - Кожный зуд ': '16',
				'25 - Пятна и высыпания':'25',
				'26 - Сыпь с температурой 🌡':'26'
			},
			'Подростки(от 11 до 18 лет)👩🏻‍🦱🧑🏻‍🦱':{
				'52 - Кожные нарушения': '52'
			}
		},
		'Заболевания мозга и психологические проблемы 🤯': {
			'Дети всех возрастов 👧🏼👦🏼': {
				'13 - Сонливость 🥱':'13',
				'17 - Обмороки, приступы головокружения и судороги 😵‍💫':'17',
				'18 - Головная боль 😣':'18',
				'19 - Неуклюжесть':'19',
				'20 - Помрачение сознания 🤪':'20',
				'21 - Нарушения речи':'21',
				'22 - Проблемы поведения':'22',
				'23 - Трудности в школе':'23'
			},
			'Подростки(от 11 до 18 лет) 👩🏼‍🦱🧑🏼‍🦱': {
				'51 - Проблемы поведения 🤪':'51',
				'53 - Нарушения веса':'53'
			}
		},
		'Глазные заболевания и нарушения зрения 🧐':{
			'27 - Глазные заболевания 👀':'27',
			'28 - Нарушения и ухудшение зрения 🧐':'28'
		},
		'Ушные заболевания и нарушения слуха 👂':{
			'29 - Боль и раздражение в ухе 😣':'29',
			'30 - Глухота 🔇':'30'
		},
		'Заболевания полости рта, языка и горла 👅🦷':{
			'32 - Боль в горле 🫢':'32',
			'36 - Зубная боль 🦷':'36'
		},
		'Заболевания системы дыхания 🦠':{
			'31 - Насморк 🤧👃':'31',
			'32 - Боль в горле 🫢':'32',
			'33 - Кашель':'33',
			'34 - Частое дыхание':'34',
			'35 - Шумное дыхание':'35'
		},
		'Заболевания органов брюшной полости и системы пищеварения у детей':{
			'Младенцы до года':{
				'4 - Кожные нарушения': '4'
			},
			'Дети всех возрастов 👧🧒🏻':{
				'16 - Кожный зуд':'16',
				'25 - Пятна и высыпания':'25',
				'26 - Сыпь с температурой 🌡':'26'
			},
			'Подростки(от 11 до 18 лет) 👩🏽‍🦱🧑🏽‍🦱':{
				'52 - Кожные нарушения': '52'
			}
		},
		'Заболевания мочевыводительной системы':{
			'43 - Нарушения мочеиспускания': '43',
			'44 - Трудности приучения к горшку':'44'
		},
		'Заболевания половых органов':{
			'48 - Заболевания половых органов у мальчиков':'48',
			'49 - Заболевания половых органов у девочек':'49'
		},
		'Заболевания мышц, костей и суставов у детей':{
			'45 - Боль в руке или в ноге 💪🏻🦵🏻':'45',
			'46 - Боли в суставах':'46',
			'47 - Заболевания стоп 🦶🏻':'47'
		}
	},
	'Общие проблемы женщин и мужчин 🤧':{
		'Проблемы общего характера 😮‍💨🤒':{
			'54 - Плохое самочувствие':'54',
			'55 - Утомляемость':'55',
			'56 - Потеря в весе':'56',
			'57 - Излишний вес':'57',
			'58 - Нарушения сна':'58',
			'59 - Высокая температура':'59'
		},
		'Заболевания кожи, волос и ногтей 👩🏻💅🏻':{
			'60 - Чрезмерная потливость':'60',
			'61 - Кожный зуд':'61',
			'62 - Припухлости и уплотнения':'62',
			'74 - Заболевания волос и кожи головы':'74',
			'75 - Заболевания ногтей':'75',
			'76 - Общие кожные нарушения':'76',
			'77 - Пятна и высыпания':'77',
			'78 - Прыщи и уплотнения на коже':'78',
			'79 - Сыпь с температурой':'79',
		},
		'Заболевания мозга и психологические проблемы':{
			'63 - Дурнота и обмороки':'63',
			'64 - Головная боль':'64',
			'65 - Головокружение':'65',
			'66 - Онемение и покалывание':'66',
			'67 - Судороги и дрожь':'67',
			'68 - Боль в области лица':'68',
			'69 - Забывчивость и помрачение сознания':'69',
			'70 - Нарушения речи':'70',
			'71 - Тревожные мысли и чувства':'71',
			'72 - Угнетенное состояние':'72',
			'73 - Беспокойство':'73',		
		},
		'Глазные заболевания и нарушения зрения':{
			'80 - Боль и раздражение глаза':'80',
			'81 - Нарушения и ухудшение зрения':'81'
		},
		'Ушные заболевания и нарушения слуха':{
			'82 - Боль в ухе':'82',
			'83 - Шум в ушах':'83',
			'84 - Глухота':'84'
		},
		'Заболевания полости рта, языка и горла':{
			'86 - Боль в горле':'86',
			'91 - Зубная боль':'91',
			'92 - Затрудненное глотание':'92',
			'93 - Заболевания слизистой рта и языка':'93'
		},
		'Заболевания системы дыхания':{
			'85 - Насморк':'85',
			'86 - Боль в горле':'86',
			'87 - Охриплость и потеря голоса':'87',
			'88 - Свистящее дыхание':'88',
			'89 - Кашель':'89',
			'90 - Затрудненное дыхание':'90',
			'106 - Боль в груди':'106',
		},
		'Сердечные заболевания':{
			'105 - Сердцебиение 💗':'105',
			'106 - Боль в груди 💔':'106'
		},
		'Заболевания органов брюшной полости и системы пищеварения':{
			'94 - Рвота':'94',
			'95 - Повторная рвота':'95',
			'96 - Боли в животе':'96',
			'97 - Повторные боли в животе':'97',
			'98 - Увеличение живота':'98',
			'99 - Газы':'99',
			'100 - Понос':'100',
			'101 - Запор':'101',
			'102 - Необычный вид кала':'102',
			'103 - Заболевания заднего прохода':'103'
		},
		'Заболевания мочевыделительной системы ☔️':{
			'104 - Расстройства мочеиспускания':'104'
		},
		'Заболевания мышц, костей и суставов 💪':{
			'107 - Боль в спине':'107',
			'108 - Боль и ограниченная подвижность шеи':'108',
			'109 - Боль в руке':'109',
			'110 - Боль в ноге':'110',
			'111 - Заболевания стоп':'111',
			'112 - Боли и опухание суставов':'112',
			'113 - Боль в колене':'113'
		}
	},
	'Специфические проблемы женщин 👩🏻':
	{
			'Беременность и роды':{
				'Нарушения во время и после беременности':{
					'138 - Тошнота и рвота при беременности':'138',
					'139 - Изменение кожи при беременности':'139',
					'140 - Боль в спине при беременности':'140',
					'141 - Изжога при беременности':'141',
					'142 - Выделения крови из влагалища':'142',
					'143 - Одышка при беременности':'143',
					'144 - Отечность голеностопных суставов':'144',
					'145 - Начались ли роды?':'145',
					'146 - Трудности грудного вскармливания':'146',
					'147 - Угнетенное состояние после родов':'147'
				}
			},
			'Проблемы женщин':
			{
				'Заболевания молочных желез':{
					'124 - Заболевания молочных желез':'124',
				},
				'Гинекологические заболевания':{
					'125 - Отсутствие менструаций':'125',
					'126 - Обильные менструации':'126',
					'127 - Болезненные менструации':'127',
					'128 - Нерегулярные выделения крови из влагалища':'128',
					'129 - Необычные выделения из влагалища':'129',
					'130 - Раздражения половых органов':'130'
				},
				'Заболевания мочевыделительной системы 🌧':{
					'131 - Непроизвольное мочеиспускание':'131',
					'132 - Болезненное мочеиспускание':'132',
					'133 - Учащенное мочеиспускание 🍉':'133',
				},
				'Проблемы секса 🙅‍♀️😐🐣':{
					'134 - Болезненный половой акт':'134',
					'135 - Снижение полового влечения':'135',
					'136 - Выбор способа предохранения':'136',
					'137 - Неспособность к зачатию':'137',
				}
			}
	},
	'Специфические проблемы мужчин 👨🏻‍🦰':{
		'Заболевания кожи головы и волос 👨‍🦲':{
			'114 - Облысение 👴':'114'
		},
		'Заболевания половых органов ♂️':
		{
			'115 - Боль и опухание яичек':'115',
			'116 - Боли в области полового члена ':'116'
		},
		'Проблемы секса 😤🙅‍♂️🐣':
		{
			'118 - Затрудненная эрекция 😤':'118',
			'119 - Преждевременное семяизвержение ⏱':'119',
			'120 - Замедленное семяизвержение ⏳':'120',
			'121 - Снижение полового влечения 🙅‍♂️':'121',
			'122 - Проблемы бесплодия':'122',
			'123 - Выбор способа предохранения для мужчин':'123'
		},
		'Заболевания мочевыделительной системы 🚰':{
			'104 - Расстройства мочеиспускания 🚽':'104',
			'117 - Болезненное мочеиспускание 😳':'117'
		}

	}
}


nav_dict = {
	'Начать диагностику ➡️' : schema_nav_dict,
	'📚 База знаний' : {
		'🚑 Первая помощь':'https://telegra.ph/Osnovy-pervoj-pomoshchi-10-08',
		'🔬 Медицинские обследования' : 'https://telegra.ph/Medicinskie-obsledovaniya-10-10',
		'🌿 Лекарственный справочник' : 'https://telegra.ph/Lekarstvennyj-spravochnik-10-10',
		'👨‍🏫 Популярная биология' : {
			'Организм ребенка 🧒' : 'https://telegra.ph/Organizm-vashego-rebenka-10-04',
			'Организм взрослого 👩🏻‍🦰' : 'https://telegra.ph/Organizm-cheloveka-10-08'
		}
	}
}



symptom_list = [	            
	            'медленная прибавка в весе',
				'пробуждения по ночам у младенца до года',
				'высокая температура у младенца до года',
				'кожные нарушения у младенца до года',
				'чрезмерный плач',
				'трудности кормления',
				'рвота у младенца до года',
				'понос у младенца до года',
				'плохое самочувствие у ребенка',
				'медленный рост у ребенка',
				'чрезмерная прибавка в весе',
				'нарушения сна у ребенка старше года',
				'сонливость у ребенка',
				'высокая температура у ребенка',
				'опухание желез у ребенка',
				'кожный зуд у ребенка',
				'обмороки, приступы головокружения и судороги у ребенка',
				'головная боль у ребенка',
				'неуклюжесть у ребенка',
				'помрачение сознания у ребенка',
				'нарушения речи у ребенка',
				'проблемы поведения у ребенка',
				'трудности в школе у ребенка',
                'Заболевания волос, кожи головы и уход за ногтями у ребенка',
                'пятна и высыпания у ребенка',
				'сыпь с температурой у ребенка',
				'глазные заболевания у ребенка',
				'нарушения и ухудшение зрения у ребенка',
                'боль и раздражение в ухе у ребенка',
				'глухота у ребенка',
				'насморк у ребенка',
				'боль в горле у ребенка',
				'кашель у ребенка',
				'частое дыхание у ребенка',
				'шумное дыхание у ребенка',
				'зубная боль у ребенка',
				'рвота у ребенка',
				'боли в животе у ребенка',
				'потеря аппетита у ребенка',
				'понос у ребенка',
				'запор у ребенка',
				'необычный вид кала у ребенка',
				'нарушения мочеиспускания у ребенка',
				'трудности приучения к горшку ребенка',
				'боль в руке или в ноге у ребенка',
				'боли в суставах у ребенка',
				'заболевания стоп у ребенка',
				'заболевания половых органов у мальчика',
				'заболевания половых органов у девочки',
				'задержание полового созревания у подростка',
				'проблемы поведения у подростка',
				'кожные нарушения у подростка',
				'нарушения веса у подростка',
                'плохое самочувствие',
				'утомляемость',
				'потеря в весе',
				'излишний вес',
				'нарушения сна',
				'высокая температура',
				'чрезмерная потливость',
				'кожный зуд',
				'припухлости и уплотнения',
				'дурнота и обмороки',
				'головная боль',
				'головокружение',
				'онемение и покалывание',
				'судороги и дрожь',
				'боль в области лица',
				'забывчивость и помрачение сознания',
				'нарушения речи',
				'тревожные мысли и чувства',
				'угнетенное состояние',
				'беспокойство',
				'заболевания волос и кожи головы',
				'заболевания ногтей',
				'общие кожные нарушения',
				'пятна и высыпания',
				'прыщи и уплотнения на коже',
				'сыпь с температурой',
				'боль и раздражение глаза',
				'нарушения и ухудшение зрения',
				'боль в ухе',
				'шум в ушах',
				'глухота',
				'насморк',
				'боль в горле',
				'охриплость и потеря голоса',
				'свистящее дыхание',
				'кашель',
				'затрудненное дыхание',
				'зубная боль',
				'затрудненное глотание',
				'заболевания слизистой рта и языка',
				'рвота',
				'повторная рвота',
				'боли в животе',
				'повторные боли в животе',
				'увеличение живота',
				'газы',
				'понос',
				'запор',
				'необычный вид кала',
				'заболевания заднего прохода',
				'расстройства мочеиспускания',
				'сердцебиение',
				'боль в груди',
				'боль в спине',
				'боль в шее',
				'боль в руке',
				'боль в ноге',
				'заболевания стоп',
				'боли и опухание суставов',
				'боль в колене',
				'облысение',
				'боль и опухание яичек',
				'боли в области полового члена',
				'болезненное мочеиспускание у мужчин',
				'затрудненная эрекция',
				'преждевременное семяизвержение',
				'замедленное семяизвержение',
				'снижение полового влечения у мужчин',
				'проблемы бесплодия у мужчин',
				'выбор способа предохранения для мужчин',
                'заболевания молочных желез',
				'отсутствие менструаций',
				'обильные менструации',
				'болезненные менструации',
				'нерегулярные выделения крови из влагалища',
				'необычные выделения из влагалища',
				'раздражение половых органов у женщин',
				'непроизвольное мочеиспускание у женщин',
				'болезненное мочеиспускание у женщин',
				'учащенное мочеиспускание у женщин',
				'болезненный половой акт у женщин',
				'снижение полового влечения у женщин',
				'выбор способа предохранения для женщин',
				'неспособность к зачатию у женщин',
				'тошнота и рвота при беременности',
				'изменения кожи при беременности',
				'боль в спине при беременности',
				'изжога при беременности',
				'выделения крови из влагалища при беременности',
				'одышка при беременности',
				'отечность голеностопных суставов у женщин',
				'начались ли роды?',
				'трудности грудного вскармливания',
				'угнетенное состояние после родов'
			]
for i in range(len(symptom_list)):
	symptom_list[i] = str(i + 1) + " - " + symptom_list[i].capitalize()

symptom_tagdict = {
	"1": ['медленная прибавка в весе','вес','недоедание','потеря аппетита','мало ест'],
	"2": ['пробужд','сон','сны','cна','ночь','просыпается ночью','не спит','спит'],
	"3": ['высокая температура','температура','лихорад','жар','горячий'],
	"4": ['кожные нарушения','пятна','дерматит','высыпания', 'экзема','родинка','меланома','сыпь','прыщ','опрелость','потница'],
	"5": ['плач','плачет','кричит','хныкать','хнычет','рыдает','истерит','орет'],
	"6": ['трудности кормления','плач','потеря аппетита','еда','есть','ест','вскармливание'],
	"7": ['рвота','тошнота','отрыжка'],
	"8": ['понос', 'несварение','крутит','жидкий','попа','ass'],
	"9": ['плохое самочувствие','сонливость', 'тело'],
	"10": ['рост','growth'],
	"11": ['вес','ожирение','толстый','weight'],
	"12": ['сон','ночь','пробужд','разбуд','недосып','спит'],
	"13": ['сонливость','усталость','апатия', 'изнемогание','тело','теле','body'],
	"14": ['температура', 'жар','тело','temperature'],
	"15": ['опухание','миндалин','железа','шея','шее','припухлость','набухание', 'свинка', 'краснуха', 'лимфа','лимфоузел'],
	"16": ['зуд','часотка','чесотка','чешется','skin'],
	"17": ['обморок','приступ','головокружение', 'судорог','голов', 'потеря cознания', 'сознание'],
	"18": ['голов','простуда','head'],
	"19": ['неуклюжесть', 'координация'],
	"20": ['неадекватность','череп','сознание','бред','голова','head'],
	"21": ['речь', 'заикание','картавость','щепелявость','развитие', 'дизлексия','speech'],
	"22": ['поведени','проблема','послушание','behaviour'],
	"23": ['школа','учеба','образование', 'усваимость','развитие','аутизм','гиперактивность','непослушный','слушает','school'],
	"24": ['волос','кож','трихофития','лыс','алопеция','вши','вошь','экзема','перхоть','себорея','skin'],
	"25": ['пятно','пятна','высыпани', 'краснуха','бородавка','фурункул', 'импетиго','сыпь','чешется','укус','насекомое','точк','дерматит','чесотка','трихофития'],
	"26": ['сыпь','оспа', 'ветрян','краснуха','корь','розеола','высыпание'],
	"27": ['глаз','глаза','веко','веки','конъюнктивит','блефарит','ячмень', 'веко', 'слезы','зрени','eye'],
	"28": ['зрени','косоглазие','туман','рефракция','глаз','глаза','близорукость','мигрень'],
	"29": ['ухо','ушная','уши','слух','насекомое','таракан','баротравма','ear'],
	"30": ['уши','ухо','слух','звук','глух', 'баротравма','ear'],
	"31": ['насморк','простуда','орви','грипп','нос'],
	"32": ['горло','горле','фарингит','тонзиллит','ангина','миндалины','throat'],
	"33": ['кашель','бронхит','харка','выделя','выделе','отхарки','коклюш','корь','бронхит','легкие','простуда','cough'],
	"34": ['дыхание','бронхит','легкие', 'астма'],
	"35": ['дыхание','легкие','трахея','астма'],
	"36": ['зуб','зубы','абсцесс','пломба','кариес','дупло','периодонт', 'десна','tooth'],
	"37": ['рвота','аппендицит','кишечник','менингит','гастроэнтерит','коклюш', 'тошнота','укачивание','гепатит'],
	"38": ['живот','гастро','рвота','грыжа','кишка','кишечник','желудок','аппендикс','аппендицит','stomach'],
	"39": ['аппетит','еда','есть','кормление','вскармливание','желтуха','мононуклеоз'],
	"40": ['понос','попа','дефекация','туалет','ass','гастро','жопа','попа','срака','кишечник','пищеварение','энкопрез','жидкий стул', 'какать','какает','срет'],
	"41": ['запор','туалет','ass''кишечник','стул','какать','shit','какает','жопа','анус','анал','сфинктер', 'попа','срака','срать'],
	"42": ['кал','какахи','дерьмо','гавно','ass','цвет','дефекация','понос','желтуха','кровь','жопа','анус','shit'],
	"43": ['моч','писать','писает','почка','почки','горшок','pee','ссать','мочится','уретра','писюн','хер','хуй','залупа','пизда','вагина','вульва'],
	"44": ['горшок','киш','какать','приучить','срать','ссать','дефекация'],
	"45": ['рука','нога','растяжение','связки','локоть','бедро','плечо', 'ушиб','перелом','кост'],
	"46": ['сустав','артроз','артрит','ревматизм','растяжение','связка','сухожилие','плечо','таз','кост'],
	"47": ['стоп','ступн','пятки','пятка','гриб','микоз','обувь'],
	"48": ['член','хуй','хер','залупа','яйц','мошонка','половой','яичк','dick','орхит','баланит','плоть','причиндал','обрезание'],
	"49": ['киска','пизда','вагина','писька','влагалища','половой','вагина','вульва','молочница','клитор'],
	"50": ['созревание','пубертат','гормон','месячные','лобок','сиськ','титьк','клитор','писька'],
	"51": ['поведение','аутизм','школа','неадекват','гиперактив','курит','курение','пьет','бухает','голова','мат','нарко','алко'],
	"52": ['кожа','угр','рубцы','рубец','прыщ','прыщи','пятн','комедон'],
	"53": ['вес','аппетит','анорексия','толст','жир','худе','сбрасыва','теря','набрал','набираю'],
	"54": ['самочувствие','беспокойство','сухожил','мышцы','мышца','усталость','раздражительность','стресс','напряжение','тревога','утомляемость','хуево','херово'],
	"55": ['утомляемость','озноб','усталость','сухожил','мышцы','мышца','одышк','недосып','лень','апатия','стресс','энерги','анемия'],
	"56": ['вес','тиреотоксикоз','диабет','анорексия','аппетит','ест','худе','сбрасыва','скидыва'],
	"57": ['жр','вес','жир','толст','полн','булимия','гипотиреоз','переедание'],
	"58": ['сон','недосып','спать','засыпа','засну','пробужд','разбуд','дрыхн','бодр','беспокойство','тревога','кофе','бессоница'],
	"59": ['температур','озноб','жар','лихорад','грипп','простуда','воспаление','орви','перегрев'],
	"60": ['пот','запах','вонь', 'нервы'],
	"61": ['зуд','кожа','чешется','чесотка','жопа','попа','срака','пизда','влагалище','вагина','перхоть','себорея','гриб'],
	"62": ['припухлость','уплотнение','грыжа','мононуклеоз','шея','узел','лимф','желез'],
	"63": ['дурно','обморок','темн','приступ','головокружение','голов','давление','гипотензия','мозг','сахар','тепловой удар','инсульт','инфаркт','миокард','спондилез'],
	"64": ['head','голов','лоб','затылок','висок','виск','грип','простуд','мозг','противозачат','контрацептив','глауком','синусит','насморк','артериит','мигрень','беспокой','томограф'],
	"65": ['голов','head','онемение','дурнота','слабость','сознание','спондилез','обморок','покалывание','равновесие','инсульт','укачив','тошнот','рвот'],
	"66": ['онемение','покалывание','обморож','мороз','рейно'],
	"67": ['судорог','свело','сводит','дрож','припадок','эпилеп','дерг','паркинсон','отрав','тиреотоксикоз'],
	"68": ['лицо','лоб','нос','лишай','переносиц','щека','щеки','ноздря','ноздри','глаз','веко','веки','глаза','нерв','губа','губы','синусит','щек','век','висок','виск'],
	"69": ['забыв','памят','сознание','мозг','речь','инсульт','стар','деменция','рассеян'],
	"70": ['реч','инсульт','паралич','картав','заика','щепеляв','гнусав','инфаркт','приступ','ишемич'],
	"71": ['тревога','беспокойство','псих','стресс','напряжение','одиноч','гомосек','гей','пидр','пидарас','ипохондри','агресси'],
	"72": ['депресс',"суицид",'самооценка','настроение','псих','упадок','стрес','недосып','либидо','пережив','беспокой','суицид','самоуби'],
	"73": ['беспокой','одышк','паник','панич','трево','страх','стрес'],
	"74": ['волос','кожа','гипотиреоз','секутся','лыс','перхоть','себорея','дерма','чешуй','псориаз'],
	"75": ['ноготь','ногти','стоп','палец','пальц','гриб','псориаз','паронихия'],
	"76": ['кожа','кожн','пузыр','перхоть','псориаз','дерма','себорея','комедон','гной','язва','гриб','прыщ','плотн','пятн','угри','чешется','чесотка','лишай','чесать','родинка','мелонома','герпес'],
	"77": ['сыпь','пятно','пятна','гриб','крапив','дерма','себорея','экзема','насеком','чешетс','чесотка','синяк'],
	"78": ['прыщ','уплотнен','прыщи','кож','родин','припухло','выпукл','себорея','мелонома','бородав','киста',],
	"79": ['сып','температур','корь','оспа','краснуха','менингит','пурпура','пузыр'],
	"80": ['глаз','глаза','веко','веки','покраснен','конъю','зрач','зрение','ирит','энтропион','глауком','блефарит','ячмень','раздражение','сухость'],
	"81": ['зрение','глаз','глаза','век','ресниц','зрач','радужка','туман','двоится','пучеглаз','экзофтальм','мигрень','линз','сетчатка','склера','двоение','мелькание','плывет','глаукома','катаракта','дальтон','косоглазие','косые','косят'],
	"82": ['ухо','уши','мочка','мочки','слух','перепонка','пробка','баротравма'],
	"83": ['шум','уши','слух','глух','звон','слыш', 'ухо'],
	"84": ['глух','слух','звук','слыш','ухо','уши', 'залож', 'меньер', 'акусти','аудио', 'пресбиакузис','отосклероз','пробка'],
	"85": ['насморк','нос','заложен','сопли','простуд','чих','кашель','орви','грип','синусит','выделени'],
	"86": ['горло','горле','гортань','рот','рту','рта','миндалин','ларингит','хрип','кашель','простуд','кашл','насморк','ангина','тонзиллит','грип','свинка','фарингит','голос'],
	"87": ['хрип','голос','связк','ларингит','простуд','горл','кашель','орви','гипотиреоз'],
	"88": ['свист','легк','харка','выделя','выделе','отхарки','мокрот','дыхание','бронхи','шум','астм'],
	"89": ['кашель','мокрот','харка','выделя','выделе','отхарки','насморк','хрип','курен','чих'],
	"90": ['дыш','дых','легкие','груд','тяжело дышать','трудно дышать','мокрота','поперхн','удуш'],
	"91": ['зуб','зубы','эмаль','десна','десны','пломб','абсцес','кариес','дупло'],
	"92": ['глот','горло','горле','ангина','тонзиллит','ком', 'фарингит','застрял'],
	"93": ['слизист','рот','небо','щека','губы','щёки','щеки','нёбо','рту','десна','десны','рта','язык','зубы','губа','десн','глоссит','молочниц', 'гингивит','заеда','герпес'],
	"94": ['рвота','крутит','блев','тошнит','тошнота','кишечник','язва','глауком','тошнот', 'гастрит','круж', 'желч','изжог'],
	"95": ['рвота','крутит','блев','кишечник','язва','глауком','тошнот', 'гастрит','круж', 'желч','изжог'],
	"96": ['живот','талия', 'коли', 'тяжесть','кишечник','желудок', 'кишка', 'печень', 'диспепсия','изжога','язва','гастроэнтерит','менструация','месячные','сальпингит'],
	"97": ['живот','талия', 'грыжа','кишечник','желудок', 'кишка', 'печень', 'колит','диспепсия','изжога','язва','гастроэнтерит','менструация','месячные','сальпингит'],
	"98": ['вздутие','тяжесть','увеличение','газ','беременность','кишечник','булимия','туловище','запор','ожирение'],
	"99": ['газ','пук','перд','рыг','дивертикулез','отрыжк','вздутие','урч','метеоризм', 'диспепсия','дефекация','мальабсорбция','коли'],
	"100": ['понос','туалет','желудок','несварение','диарея','кишечник','живот','язва','кровь','гастро','дизентерия','коли','дивертикулез'],
	"101": ['запор','туалет','какат','кишечник','срать','срет','дефекация','очко','жопа','попа','срака','зад'],
	"102": ['кал','какахи','дерьмо','гавно','ass','цвет','мальабсорбция','колоноскопия','гемор','дефекация','понос','желтуха','кровь','жопа','анус','shit'],
	"103": ['очко','зад','жопа','анус','сфинктер','анал','простат','гемор','кровотечение','глист','зуд','кишка','отверстие'],
	"104": ['моча','писать','задерж','недерж','писает','почк','pee','ссать','мочит','пенис','предстат','уретра','пизда','вагина','вульва'],
	"105": ['сердце','сердеч','учащен','беспокойство','тревога','биение','ритм','анемия','тахикардия','экг','кофе'],
	"106": ['клетк','груд','харка','выделя','выделе','отхарки','мокрот','диспепсия','эмболия','серд','легкие','легоч','приступ','ишемич','стенокардия','одышка','бронх','мокрот'],
	"107": ['спин','поясница','позвон','ягодиц','нерв','грыжа','растяжени','ушиб', 'смещение','спондилез'],
	"108": ['подвижность','шея','шей','шее','шею','менингит','спондилез','смещение'],
	"109": ['рук','плеч','кист','палец','пальц','локот','мышц','перелом','растя','вывих','кост','бурсит','запяст','ушиб'],
	"110": ['ног','бедр','растя','перелом','ушиб','вывих','тромбо','варикоз','голень','икра','щиколотка'],
	"111": ['стоп','зуд','пятка','пятки','жжение','растяжение','пальц','палец','ушиб','перелом','мозол','бородав','гриб','микоз','чешетс','бурсит','ногот','ногт'],
	"112": ['сустав','растя','таз','сухожил','голен','кост','связк','хрящ','мышц','вывих','подагр','артрит','ревмат','артроз','бурсит'],
	"113": ['колен','чашк','бурсит','артрит','хрящ'],
	"114": ['лыс','плеш','волос','выпад','гриб','гормон'],
	"115": ['яйц','яич','яиц','опух','припух','орхит','мошонк','перекрут','киста','гидроцеле'],
	"116": ['член','хуй','хер','пенис','залуп','уретр','дроч','мастур','онанизм','головк','баланит','фалос','эрекция','плоть','приепизм','обрезание','венер','уролог','секс','генитали','сперм'],
	"117": ['моча','писать','писает','почк','горшок','pee','мастур','ссать','венер','герпес','секс','простат','мочится','уретра','писюн','член','хер','хуй','залупа'],
	"118": ['эрекци', 'член','хер','хуй','залупа','фалос','пенис','не встает','либидо','секс','возбужд','мастурб','онанизм','влечение'],
	"119": ['преждевремен','семяизверж','конча', 'интим','сперм','член','хер','хуй','залупа','фалос','пенис','кончи','эякуляц','секс','дроч','мастурб','онанизм'],
	"120": ['замедлен','семяизверж','конча','интим','эякуляц','сперм','кончи','секс','дроч','мастурб','онанизм'],
	"121": ['влечени','либидо','секс','интим','возбужд','гормон','эрекц','тестостерон','стресс','ориентац','геи','пидор'],
	"122": ['бесплод','паротит','зачат','сперм','конч','секс','орхит','венер','заберемен'],
	"123": ['зачат','презерват','контрацепт','гандон','вазэктомия','предохран','сперма'],
	"124": ['желез','молок','молоч','груд','сиськ','титьк','вскармливан','кормл','сосок','соск','маммо'],
	"125": ['менструац','овуляц','влагалищ','труб','вагин','вульв','менопауз','матк','аменор','месячн','пизд','киск','беремен','вульв','кровотеч'],
	"126": ['менструац','овуляц','влагалищ','труб','вагин','вульв','вульв','менопауз','месячн','матк','пизд','киск','беремен','вульв','кровотеч'],
	"127": ['менструац','овуляц','влагалищ','вагин','труб','менопауз','сальпингит','прогестерон','месячн','матк','пизд','киск','беремен','вульв','кровотеч'],
	"128": ['выделен','овуляц','кров','вульв','труб','гистерэктом','влагалищ','менструац','вагин','менопауз','сальпингит','прогестерон','месячн','матк','пизд','киск','беремен','вульв','кровотеч'],
	"129": ['выделен','поллюц','овуляц','влагалищ','труб','молочниц','вульв','секс','сифилис','гоноре','герпес','хламидо','венер','трихомонад','вагинит','кольпит','менструац','вагин','менопауз','сальпингит','прогестерон','месячн','матк','пизд','киск','беремен','вульв','кровотеч'],
	"130": ['зуд','раздражени','генитал','труб','влагалищ','кож','вагин','вульв','матк','пизд','клитор','лобок','лобк'],
	"131": ['моч','писать','писает','почк','унитаз','туалет','pee','ссать','мочится','пизда','вагина','вульва','непроизвол'],
	"132": ['моч','писать','писает','почк','трихомонад','молоч','цистит','уретрит','унитаз','туалет','pee','ссать','мочится','труб','пизда','вагина','вульва'],
	"133": ['моч','писать','пузыр','писает','почк','трихомонад','молоч','цистит','уретрит','унитаз','туалет','pee','ссать','мочится','пизда','вагина','вульва'],
	"134": ['акт','секс','половой','влагалищ','интим','вагин','влагалищ','вульв','эндометриоз','кист','яичн'],
	"135": ['влечен','сношен','либид','секс','интерес','возбуд','возбужд','ориентаци','гомосек','вагин','влагалищ','гормон'],
	"136": ['предохран','презерв','контрацеп','барьер','гандон','таблетк','зачат','беремен','стерилиз','прерывани','аборт','овуляц','месяч','эстрог','гормон'],
	"137": ['бесплод','гормон','зачат','заберемен','секс','месяч','овуляц','сальпингит'],
	"138": ['беремен','тошн','рвот','головокруж','гиперемезис'],
	"139": ['беремен','кож','экзем','хлоазма','гормон','прогестерон','сухость','растяжен','полос'],
	"140": ['беремен','спин','схватк','поясниц'],
	"141": ['изжог','беремен','пищевод','жжет','жжение'],
	"142": ['выделен','беремен','овуляц','выкидыш','кров','вульв','гистерэктом','влагалищ','менструац','вагин','менопауз','сальпингит','прогестерон','месячн','матк','пизд','киск','беремен','вульв','кровотеч'],
	"143": ['одышк','беремен','дыхан','легкие','дышат','груд'],
	"144": ['беремен','отечн','отек','лодыж','голен','сустав','преэклампси'],
	"145": ['роды','беремен','рожае','отхождение вод'],
	"146": ['груд','вскармливан','кормлен','молок'],
	"147": ['послеродовая','депрес','угнетен','беремен','меланхоли']
}

links_dict = {
	"appendicit.png" : ["Боль при аппендиците","Удаление аппендикса"],
	"boleznennost.png": ["Менструальный цикл","Лечение менструальных состояний"],
	"diafragma.png":["Как похудеть"],
	"ekzema_golovy.png":["Себорейный дерматит","Экзема"],
	"golod.png":["Частота кормлений и дополнительное питье"],
	"migren.png":["Как облегчить головную боль у ребенка"],
	"perhot.png":["Себорейный дерматит","Экзема"],
	"perhot_deti.png":["Себорейный дерматит","Экзема"],
	"podagra.png":["Анализ крови"],
	"povtornie_boli.png":["Боль при аппендиците"],
	"razriv.png":["Стимуляция родов"],
	"recs_orvi.png":["Как снизить у ребенка температуру"],
	"seboreya.png":["Экзема головы", "Уход за кожей младенца"],
	"skin_irritation.png":["Уход за кожей младенца"],
	"spondilez.png":["Рентгенологическое исследование костей"],
	"stenokardiya.png":["Электрокардиография(ЭКГ)","Рентгенография грудной клетки","Ишемическая болезнь сердца(ИБС)"],
	"vipadenie_diska.png":["Рентгенологическое исследование костей"],
	"vospalenie_putey.png":["Как собрать среднюю порцию мочи у ребенка","Профилактика инфекции мочевыводящих путей"],
	"1": {
		"info0":["10 - Медленный рост", "Показатели физического развития детей", "Варианты роста в грудном возрасте", "Взвешивание и измерение младенцев и детей"],
		"nyn":["Грудное и искусственное вскармливание"],
		"nnn":["Потеря веса у новорожденных"],
		"y":["Потеря веса у новорожденных"],
		"nyy":["Потеря веса у новорожденных"],
		"nnyynn":["Потеря веса у новорожденных"],
		"nnyyny":["Потеря веса у новорожденных"]
	},
	"2":{
		"info0":["5 - Чрезмерный плач", "12 - Нарушения сна у ребенка","29 - Боль и раздражение в ухе"],
		"nnnnn":["Как улучшить сон ребенка", "Периоды сна и бодрствования ребенка"],
		"nnnny":["Как улучшить сон ребенка","Периоды сна и бодрствования ребенка"],
		"nnny":["Периоды сна и бодрствования ребенка"],
		"nny":["Периоды сна и бодрствования ребенка"],
		"nyny":["29 - Боль и раздражение в ухе"],
		"nyy":["3 - Высокая температура у младенца","5 - Чрезмерный плач у младенца"],
		"ynn":["Голод"],
		"ynynnnnn":["Как улучшить сон ребенка","Периоды сна и бодрствования ребенка"],
		"ynynnnny":["Как улучшить сон ребенка","Периоды сна и бодрствования ребенка"],
		"ynynyny":["29 - Боль и раздражение в ухе"],
		"ynynynnnnn":["Как улучшить сон ребенка","Периоды сна и бодрствования ребенка"],
		"ynynynnnny":["Как улучшить сон ребенка","Периоды сна и бодрствования ребенка"],
		"ynyy":["Частота кормлений и дополнительное питье"],
		"yy":["5 - Чрезмерный плач"]
	},
	"3":{
		"info0":["Вирусные и бактериальные инфекции у детей","14 - Высокая температура"],
		"info1":["Как снизить у ребенка температуру","с.83 - Электроэнцефалография"],
		"nnn":["Частота дыхания у ребенка"],
		"nnnnnnny":["Как лечить больное горло", "Опасные симптомы у ребенка"],
		"nnnnnny":["Лечение диспепсии у младенцев","Упорная рвота"],
		"nnnnny":["Люмбальная пункция у детей"],
		"nnnny":["Сравнительная характеристика детских инфекций", "Как снизить у ребенка температуру"],
		"ny":["26 - Сыпь с температурой"],
		"y":["Как снизить у ребенка температуру"]
	},
	"4":{
		"info0":["24 - Заболевания волос, кожи головы, уход за ногтями у ребенка","25 - Пятна и высыпания у ребенка"],
		"nnnyn":["Сравнительная характеристика детских инфекций"],
		"nnyn":["Уход за кожей младенца"],
		"nnyy":["Уход за кожей младенца","8 - Понос"],
		"ynnnyn":["Сравнительная характеристика детских инфекций"],
		"ynnyn":["Уход за кожей младенца"],
		"ynnyy":["Уход за кожей младенца","8 - Понос"],
		"yny":["Себорейный дерматит"],
		"yy":["Экзема головы","Уход за кожей младенца"]
	},
	"5":{
		"info0":["6 - Трудности кормления младенцев", "9 - Плохое самочувствие у ребенка"],
		"nnnyyy":["Заглатывание воздуха"],
		"nny":["Частота кормлений и дополнительное питье"],
		"ny":["Частота кормлений и дополнительное питье"],
		"ynnnyyy":["Заглатывание воздуха"],
		"ynny":["Частота кормлений и дополнительное питье"],
		"yny":["Частота кормлений и дополнительное питье"],
		"yyy":["Заглатывание воздуха","Уход за кожей младенца","Раздражение кожи при опрелостях"]
	},
	"6":{
		"info0":["5 - Чрезмерный плач", '39 - Потеря аппетита', "44 - Трудности приучения к горшку ребенка"],
		"info3":["Составные части рационального питания"],
		"nnny":["Отнятие от груди","Составные части рационального питания","Варианты роста в грудном возрасте"],
		"nnyny":["Отнятие от груди","Составные части рационального питания","Варианты роста в грудном возрасте"],
		"nnyy":["5 - Чрезмерный плач"],
		"nynnnny":["Отнятие от груди","Составные части рационального питания","Варианты роста в грудном возрасте"],
		"nynnny":["5 - Чрезмерный плач"],
		"nyny":["Частота кормлений и дополнительное питье"],
		"nyy":["Варианты роста в грудном возрасте"],
		"nyyn":["Грудное и искусственное вскармливание"],
		"nyyy":["Частота кормлений и дополнительное питье","5 - Чрезмерный плач"],
		"yn":["Варианты роста в грудном возрасте"]
	},
	"7":{
		"info0":["8 - Понос у младенца до года","37 - Рвота у детей старше года"],
		"nny":["Лечение диспепсии у младенцев","Предостережение"],
		"nynnn":["3 - Высокая температура у младенца"],
		"nynny":["Лечение диспепсии у младенцев","Предостережение"],
		"nyy":["Вирусные и бактериальные инфекции у детей", "Люмбальная пункция у детей"],
		"ynnny":["Лечение диспепсии у младенцев","Предостережение"],
		"ynnynnn":["3 - Высокая температура у младенца"],
		"ynnynny":["Лечение диспепсии у младенцев","Предостережение"],
		"ynnyy":["Вирусные и бактериальные инфекции у детей", "Люмбальная пункция у детей"],
		"ynynny":["Лечение диспепсии у младенцев","Предостережение"],
		"ynynynnn":["3 - Высокая температура у младенца"],
		"ynynynny":["Лечение диспепсии у младенцев","Предостережение"],
		"ynynyy":["Вирусные и бактериальные инфекции у детей", "Люмбальная пункция у детей"],
		"yy":["Заглатывание воздуха"]
	},
	"8":{
		"info0":["40 - Понос у детей старше года","42 - Необычный вид кала у ребенка"],
		"info2":["Упорная рвота"],
		"nny":["Лечение диспепсии у младенцев"],
		"ny":["Лечение диспепсии у младенцев"],
		"y":["Лечение диспепсии у младенцев"]
	},
	"9":{
		"info0":["Плохое самочувствие у детей до двух лет", "13 - Сонливость"],
		"info1":["Частота дыхания у ребенка"],
		"info3":["Осмотр ушей у ребенка"],
		"nnnnnny":["23 - Трудности в школе"],
		"nnnnny":["38 - Боли в животе у ребенка"],
		"nnnny":["Сравнительная характеристика детских инфекций"],
		"nnny":["Сравнительная характеристика детских инфекций", "25 - Пятна и высыпания у детей"],
		"nnyn":["32 - Боль в горле у ребенка"],
		"y":["14 - Высокая температура у ребенка"]
	},
	"10":{
		"info0":["Показатели физического развития детей","1 - Медленная прибавка в весе"],
		"info1":["с.302 - Номограммы физического развития мальчиков","с.303 - Номограммы физического развития девочек","11 - Чрезмерная прибавка в весе у детей","50 - Задержка полового созревания"],
	},
	"11":{
		"info0":["Взвешивание и измерение младенцев и детей","Показатели физического развития детей"],
		"info1":["Составные части рационального питания"],
		"nnn":["Как помочь вашему ребенку похудеть"],
		"ny":["Причины чрезмерной прибавки в весе"],
		"yny":["Составные части рационального питания"]
	},
	"12":{
		"info0":["2 - Пробуждения по ночам у детей до 1 года", "58 - Нарушения сна"],
		"info2":["Как улучшить сон ребенка"],
		"nnn":["Предупреждение и преодоление нарушений сна"],
		"ynnnnnn":["Предупреждение и преодоление нарушений сна"],
		"ynnny":["43 - Нарушения мочеиспускания у детей"],
		"yy":["5 - Чрезмерный плач","14 - Высокая температура у ребенка","31 - Насморк у ребенка"]
	},
	"13":{
		"info0":["12 - Нарушения сна у ребенка", "17 - Обмороки, приступы головокружения и судороги у ребенка"],
		"info3":["Курение, употребление алкоголя и наркотиков у подростков"],
		"nnny":["Компьютерная томография черепа ребенка(КТ)"],
		"nny":["25 - Пятна и высыпания у детей"],
		"ny":["Первая помощь при отравлениях"],
		"y":["Люмбальная пункция у детей"]
	},
	"14":{
		"info0":["Вирусные и бактериальные инфекции у детей","Как измерить температуру у ребенка","3 - Высокая температура у ребенка до года"],
		"info1":["Как измерить температуру у младенца"],
		"info3":["Как снизить у ребенка температуру","c.83 - Электроэнцефалография"],
		"nnnnnnny":["Как собрать среднюю порцию мочи у ребенка"],
		"nnnnny":["Лечение гастроэнтерита у детей"],
		"nnnny":["Люмбальная пункция у детей"],
		"nnny":["Сравнительная характеристика детских инфекций"],
		"nnyn":["Частота дыхания у ребенка"],
		"nnynnn":["Как снизить у ребенка температуру"],
		"nnynny":["Сравнительная характеристика детских инфекций","Как снизить у ребенка температуру"],
		"ny":["Как облегчить ушную боль у ребенка"],
		"y":["26 - Сыпь с температурой"]
	},
	"15":{
		"info0":["Сравнительная характеристика детских инфекций","Лимфатические железы","62 - Припухлости и уплотнения"],
		"nnnny":["Бородавки и фурункулы"],
		"nnnyny":["Бородавки и фурункулы"],
		"nnnyy":["Вирусные и бактериальные инфекции у детей","Как лечить больное горло","Опасные симптомы у ребенка","Тонзиллэктомия(удаление миндалин)","Что такое миндалины?"],
		"nny":["Сравнительная характеристика детских инфекций"],
		"y":["Сравнительная характеристика детских инфекций"]
	},
	"16":{
		"info0":["25 - Пятна и высыпания у детей","61 - Кожный зуд"],
		"nnnnynn":["Экзема", "Рекомендации при кожном зуде"],
		"nnnnn":["Экзема","Рекомендации при кожном зуде"],
		"nnny":["48 - Заболевания половых органов у мальчиков","49 - Заболевания половых органов у девочек"],
		"ny":["24 - Заболевания волос, кожи головы и уход за ногтями у ребенка"],
		"y":["25 - Пятна и высыпания"]
	},
	"17":{
		"info0":["13 - Сонливость у ребенка","19 - Неуклюжесть у ребенка"],
		"info1":["с.284: Основы первой помощи. Порядок неотложных действий","с.285: Дыхание рот-в-рот. Правильное положение пострадавшего","с.286: Первая помощь при утоплении. Остановка кровотечений","с.287 - Первая помощь при удушье, шоке, ударе электрическим током, потере сознания","Первая помощь при отравлениях","с.289 - Первая помощь при переохлаждении,обморожении,укасах,тепловом ударе и анафилактическом шоке"],
		"nnny":["Первая помощь при обмороке у детей"],
		"nny":["Эпилепсия"],
		"ny":["Строение уха"],
		"ynn":["Первая помощь при обмороке у детей"],
		"ynyn":["Эпилепсия"],
		"ynyy":["Судороги при высокой температуре"],
		"yyn":["Эпилепсия"],
		"yyy":["Судороги при высокой температуре"]
	},
	"18":{
		"info0":["14 - Высокая температура у ребенка","64 - Головная боль"],
		"nnn":["Как облегчить головную боль у ребенка"],
		"nny":["Как облегчить головную боль у ребенка"],
		"nynnnnnn":["Как облегчить головную боль у ребенка"],
		"nynnnnny":["Как облегчить головную боль у ребенка"],
		"nynnnny":["Как облегчить головную боль у ребенка"],
		"nynnny":["Как облегчить головную боль у ребенка"],
		"nynny":["Проверка зрения у ребенка"],
		"nyny":["Как облегчить головную боль у ребенка"],
		"nyy":["Мигрень у ребенка"],
		"ynnny":["37 - Рвота у детей"],
		"ynny":["14 - Высокая температура у ребенка"],
		"ynynny":["37 - Рвота у детей"],
		"ynyny":["14 - Высокая температура у ребенка"],
		"ynyy":["Как лечить простуду у ребенка"],
		"yy":["Вирусные и бактериальные инфекции у детей","Люмбальная пункция у детей"]
	},
	"19":{
		"info0":["13 - Сонливость у ребенка","17 - Обмороки, приступы головокружения и судороги у ребенка"],
		"ny":["Развитие навыков и ловкости рук"],
		"y":["Развитие навыков и ловкости рук"]
	},
	"20":{
		"info0":["21 - Нарушения речи у ребенка","22 - Проблемы поведения у ребенка"],
		"nny":["Вирусные и бактериальные инфекции у детей","Люмбальная пункция у детей"],
		"ny":["Судороги при высокой температуре","Как снизить у ребенка температуру","14 - Высокая температура у ребенка"],
		"y":["Компьютерная томография черепа ребенка(КТ)"]
	},
	"21":{
		"info0":["19 - Неуклюжесть у ребенка","23 - Трудности в школе у ребенка"],
		"ynn":["Осмотр ушей у ребенка","Как вы можете помочь развитию речи у вашего ребенка"],
		"ynyn":["Проверка слуха у детей", "Осмотр ушей у ребенка", "30 - Глухота"],
		"yyy":["Помощь развитию речи у ребенка"]
	},
	"22":{
		"info0":["23 - Трудности в школе у ребенка","51 - Проблемы поведения подростков"],
		"nnnny":["Курение, употребление алкоголя и наркотиков у подростков"],
		"nnnyn":["Одаренные дети","Типы проблем поведения у детей","Правила поведения и дисциплина","Детская консультация"],
		"nnnyy":["Типы проблем поведения у детей","Правила поведения и дисциплина"],
		"nyn":["Типы проблем поведения у детей","Гиперактивность"],
		"nny":["23 - Трудности в школе"],
		"nyy":["Типы проблем поведения у детей","Ужасные двухлетки","Правила поведения и дисциплина","Детская консультация"],
		"y":["51 - Проблемы поведения у подростков"]
	},
	"23":{
		"info0":["22 - Проблемы поведения у ребенка","51 - Проблемы поведения подростков"],
		"info1":["Проблемы обучения у ребенка"],
		"info3":["Дизлексия у детей"],
		"nny":["Одаренные дети", "51 - Проблемы поведения у подростков","Правила поведения и дисциплина"],
		"ynnnny":["Одаренные дети", "51 - Проблемы поведения у подростков","Правила поведения и дисциплина"],
		"yy":["Проблемы обучения у ребенка"]
	},
	"24":{
		"info0":["16 - Кожный зуд у ребенка","25 - Пятна и высыпания у ребенка"],
		"nnnny":['Перхоть у детей'],
		"nynn":["Составные части рационального питания"]
	},
	"25":{
		"info0":["4 - Кожные нарушения у детей", "26 - Сыпь с температурой"],		
		"nnnnny":["52 - Кожные нарушения у подростков"],
		"nnny":["Сравнительная характеристика детских инфекций"],
		"y":["26 - Сыпь с температурой"]
	},
	"26":{
		"info0":["Сравнительная характеристика детских инфекций", "14 - Высокая температура","25 - Пятна и высыпания у ребенка"],
		"info1":["Частота дыхания у ребенка"],
		"nnyyn":["Прививки для детей","Как снизить у ребенка температуру"],
		"nyn":["Сравнительная характеристика детских инфекций"],
		"nyy":["Сравнительная характеристика детских инфекций","Как снизить у ребенка температуру"],
		"y":["Сравнительная характеристика детских инфекций","Как снизить у ребенка температуру"]
	},
	"27":{
		"info0":["28 - Нарушения и ухудшение зрения у ребенка", "80 - Боль и раздражение глаза"],
		"nnyn":["Меры для лечения вирусного конъюктивита"],
		"ny":["Первая помощь при травмах глаза у детей"],
		"y":["Первая помощь при травмах глаза у детей"]
	},
	"28":{
		"info0":["27 - Глазные заболевания у ребенка","81 - Нарушения и ухудшение зрения"],
		"nnyny":["Первая помощь при отравлениях"],
		"ny":["Косоглазие"],
		"yy":["Компьютерная томография черепа ребенка(КТ)"]
	},
	"29":{
		"info0":["82 - Боль в ухе","30 - Глухота у ребенка"],
		"ynn":["Как облегчить ушную боль у ребенка"],
		"yny":["Как облегчить ушную боль у ребенка"],
		"yy":["Как облегчить ушную боль у ребенка"]
	},
	"30":{
		"info0":["21 - Нарушения речи у ребенка", "29 - Боль и раздражение в ухе у ребенка", "84 - Глухота"],
		"info1":["Удаление аденоидов"],
		"nnn":["Закупорка наружного слухового прохода"],
		"ny":["Миринготомия и установка шунта"],
		"ynnn":["Осмотр ушей у ребенка"],
		"yy":["Осмотр ушей у ребенка"]
	},
	"31":{
		"info0":["32 - Боль в горле у ребенка","33 - Кашель у ребенка"],
		"info1":["Частота дыхания у ребенка"],
		"info2":["Как снизить у ребенка температуру"],
		"nnn":["Как лечить простуду у ребенка"],
		"ny":['Рекомендации при общем вирусном заболевании'],
		"ynn":["Как лечить простуду у ребенка"],
		"ynyn":["Как лечить простуду у ребенка"],
		"yy":["Как снизить у ребенка температуру"]
	},
	"32":{
		"info0":["31 - Насморк у ребенка","33 - Кашель у ребенка"],
		"info1":["Удаление аденоидов"],
		"nn":["Опасные симптомы у ребенка"],
		"ny":["Как лечить простуду у ребенка"],
		"yn":["Вирусные и бактериальные инфекции у детей", "Как лечить больное горло","Опасные симптомы у ребенка","Тонзиллэктомия(удаление миндалин)"],
		"yy":["Сравнительная характеристика детских инфекций"]
	},
	"33":{
		"info0":["87 - Охриплость и потеря голоса","89 - Кашель"],
		"nn":["Частота дыхания у ребенка"],
		"nnnnnnnny":["22 - Проблемы поведения у детей"],
		"nnnnnnyy":["Удаление аденоидов"],
		"nnnnnnyn":["Вирусные и бактериальные инфекции у детей","Как лечить простуду у ребенка"],
		"nnnnnyy":["Как лечить простуду у ребенка"],
		"nnnynn":["Как снизить у ребенка температуру"],
		"nnnyny":["Сравнительная характеристика детских инфекций","Как снизить у ребенка температуру"],
		"nny":["34 - Частое дыхание у ребенка"],
		"ny":["35 - Шумное дыхание у ребенка"]
	},
	"34":{
		"info0":["Частота дыхания у ребенка", "35 - Шумное дыхание у ребенка","90 - Затрудненное дыхание"],
		"nny":["33 - Кашель у ребенка","13 - Сонливость у детей"],
		"ny":["Первая помощь при удушье"],
		"y":["35 - Шумное дыхание у ребенка"]
	},
	"35":{
		"info0":["34 - Частое дыхание","88 - Свистящее дыхание","90 - Затруденное дыхание"],
		"info1":["Частота дыхания у ребенка"],
		"nn":["Опасные симптомы у детей"],
		"nnnn":["Опасные симптомы у детей", "Всё об астме"],
		"nnny":["Опасные симптомы у детей", "Всё об астме"],
		"nny":["Всё об астме"],
		"ny":["Частота дыхания у ребенка"],
		"nyy":["Дыхание рот-в-рот и рот-в-нос"],
		"y":["Первая помощь при удушье"]
	},
	"36":{
		"info0":["91 - Зубная боль", "Как облегчить зубную боль у ребенка"],
		"y":["Как облегчить зубную боль у ребенка","Другие заболевания, вызывающие зубную боль"],
		"ny":["Как облегчить зубную боль у ребенка", "Профилактика кариеса", "Другие заболевания, вызывающие зубную боль"],
		"nnyn":["Как облегчить зубную боль у ребенка", "Другие заболевания, вызывающие зубную боль"],
		"nnnnn":["Как облегчить зубную боль у ребенка", "Другие заболевания, вызывающие зубную боль"],
		"nnny":["Профилактика кариеса", "Другие заболевания, вызывающие зубную боль"],
		"nnnny":["Другие заболевания, вызывающие зубную боль", "Как облегчить зубную боль у ребенка"]
	},
	"37":{
		"info0":["Что делать, когда у ребенка рвота","Опасные симптомы при рвоте", "7 - Рвота у ребенка до года"],
		"info3":["Лечение диспепсии у младенцев"],
		"nnnnnnnn":["Что делать, когда у ребенка рвота"],
		"nnnnnnny":["Лечение диспепсии у младенцев"],
		"nnnnnny":["Что делать, когда у ребенка рвота", "23 - Трудности в школе"],
		"nnnnny":["Строение мочевыделительной системы","Как собрать среднюю порцию мочи у ребенка"],
		"nnnny":["Лечение гастроэнтерита у детей"],
		"nnny":["33 - Кашель у детей","35 - Шумное дыхание"],
		"nnyn":["13 - Сонливость у детей","Вирусные и бактериальные инфекции у детей","Люмбальная пункция у детей"],
		"y":["Удаление аппендикса"],
	},
	"38":{
		"info0":["37 - Рвота у ребенка", "Опасные симптомы при болях в животе"],
		"info2":["Опасные симптомы при болях в животе"],
		"nnnnnnn":["Опасные симптомы при болях в животе"],
		"nnnnnnyn":["Опасные симптомы при болях в животе"],
		"nnnnny":["Опасные симптомы при болях в животе","Как лечить простуду у ребенка","Как лечить больное горло"],
		"nnnny":["Строение мочевыделительной системы","Как собрать среднюю порцию мочи у ребенка"],
		"nnny":["Аппендицит","Боль при аппендиците"],
		"nnynn":["Лечение гастроэнтерита у детей","Повторные боли в животе у ребенка","Аппендицит","Боли при аппендиците"],
		"nnyy":["Лечение гастроэнтерита у детей","Опасные симптомы при болях в животе"],
		"y":["Боль при аппендиците","Удаление аппендикса"]
	},
	"39":{
		"info0":["Варианты роста в детском возрасте","6 - Трудности кормления","32 - Боль в горле у ребенка"],
		"info1":["Варианты роста в детском возрасте","53 - Нарушения веса у подростков"],
		"info2":["Капризы в еде"],
		"n":["Варианты роста в детском возрасте"],
		"nnnnn":["Капризы в еде"],
		"nnnny":["Как собрать среднюю порцию мочи у ребенка","Профилактика инфекции мочевыводящих путей"],
		"ynnn":["Капризы в еде"],
		"ynny":["32 - Боль в горле у детей"],
		"yny":["25 - Пятна и высыпания у детей"],
		"yy":["14 - Высокая температура у детей"]
	},
	"40":{
		"info0":["Лечение гастроэнтерита у детей","8 - Понос у детей до года","100 - Понос"],
		"info3":["Лечение диспепсии у младенцев","Опасные симптомы при поносе"],
		"nnyy":["Детская консультация"],
		"nynyy":["Детская консультация"],
		"nyynyy":["Детская консультация"],
		"ynnn":["Лечение гастроэнтерита у детей"],
		"ynny":["Лечение гастроэнтерита у детей"],
		"yny":["Лечение гастроэнтерита у детей"],
		"yy":["Лечение гастроэнтерита у детей"]
	},
	"41":{
		"info0":["38 - Боли в животе у ребенка", "101 - Запор"],
		"nyy":["Трещина в заднем проходе"],
		"ynnnny":["Как приучить ребенка к горшку"],
		"ynny":["14 - Высокая температура у ребенка","37 - Рвота у детей"],
		"yy":["38 - Боли в животе"]
	},
	"42":{
		"info0":["38 - Боли в животе","40 - Понос у ребенка"],
		"info1":["41 - Запор у ребенка","Трещина в заднем проходе"],
		"yny":["8 - Понос"]
	},
	"43":{
		"info0":["44 - Трудности приучения к горшку","104 - Расстройства мочеиспускания"],
		"nynnny":["Как собрать среднюю порцию мочи у ребенка"],
		"nynny":["Всё об астме","34 - Частое дыхание у ребенка"],
		"nynynny":["Как собрать среднюю порцию мочи у ребенка"],
		"nynyny":["Всё об астме","34 - Частое дыхание у ребенка"],
		"nyy":["Профилактика инфекции мочевыводящих путей", "14 - Высокая температура у ребенка"],
		"y":["Как собрать среднюю порцию мочи у ребенка","Профилактика инфекции мочевыводящих путей"]
	},
	"44":{
		"info0":["6 - Трудности кормления","22 - Проблемы поведения у ребенка","Как приучить ребенка к горшку"],
		"nnnynn":["Как приучить ребенка к горшку"],
		"nnnyy":["Как собрать среднюю порцию мочи у ребенка"],
		"nnyn":["Как собрать среднюю порцию мочи у ребенка", "Как приучить ребенка к горшку"],
		"nnyy":["Как приучить ребенка к горшку"],
		"nynnnynn":["Как приучить ребенка к горшку"],
		"nynnnyy":["Как собрать среднюю порцию мочи у ребенка"],
		"nynnyn":["Как собрать среднюю порцию мочи у ребенка","Как приучить ребенка к горшку"],
		"nynnyy":["Как приучить ребенка к горшку"],
		"y":["Как приучить ребенка к горшку"]
	},
	"45":{
		"info0":["109 - Боль в руке","110 - Боль в ноге"],
		"info2":["с.286 - Первая помощь при кровотечениях"],
		"nnny":["Боли, связанные с ростом"],
		"ny":["46 - Боли в суставах"],
		"yn":["Первая помощь при подозрении на перелом кости или вывих у ребенка"],
		"yy":["Первая помощь при растяжениях у ребенка"]
	},
	"46":{
		"info0":["45 - Боль в руке или в ноге у ребенка","112 - Боли и опухание суставов"],
		"info1":["Бородавки и фурункулы","45 - Боль в руке или в ноге","46 - Боли в суставах","47 - Заболевания стоп"],
		"info2":["Первая помощь при подозрении на перелом кости или вывих у ребенка"],
		"info3":["Первая помощь при потере сознания"],
		"nynnn":["Первая помощь при растяжениях у ребенка"],
		"nynny":["Первая помощь при растяжениях у ребенка"],
		"nyny":["14 - Высокая температура у ребенка"],
		"nyy":["14 - Высокая температура у ребенка"],
		"yn":["Первая помощь при растяжениях у ребенка"],
		"yy":["Первая помощь при подозрении на перелом кости или вывих у ребенка"]
	},
	"47":{
		"info0":["111 - Заболевания стоп"],
		"info1":["Уход за ногтями"],
		"nnnyn":["Уход за стопами ребенка"],
		"ynyny":["Уход за стопами ребенка"],
		"ynyy":["Бородавки и фурункулы"],
		"yyn":["Первая помощь при подозрении на перелом кости или вывих у ребенка"],
		"yyy":["Первая помощь при растяжениях у ребенка"]
	},
	"48":{
		"info0":["115 - Боль и опухание яичек","116 - Боли в области полового члена"],
		"info2":["Обрезание у детей"],
		"info4":["Сужение крайней плоти у мальчика"],
		"nnnny":["Инородное тело в мочеиспускательном канале"],
		"nny":["Как собрать среднюю порцию мочи у ребенка"]
	},
	"49":{
		"info":["130 - Раздражение половых органов у женщин","132 - Болезненное мочеиспускание у женщин"],
		"nny":["Основные вехи нормального развития подростка"],
		"nyn":["Воспаление мочевыводящих путей","Как собрать среднюю порцию мочи у ребенка","Что делать при раздражении половых органов"],
	},
	"50":{
		"info0":["Основные вехи нормального развития подростка","53 - Нарушения веса у подростка"],
		"info1":["с.300 - Измерение окружности головы у ребенка","с.301 - Номограмма роста","с.302 - Номограммы физического развития мальчиков","с.303 - Номограммы физического развития девочек"],
		"nnny":["Показатели физического развития детей"],
		"ynny":["Показатели физического развития детей"],
	},
	"51":{
		"info0":["22 - Проблемы поведения детей", "23 - Трудности в школе"],
		"nny":["52 - Кожные нарушения","53 - Нарушения веса у ребенка"],
		"ny":["Капризы в еде","53 - Нарушения веса"],
		"ynnnnny":["52 - Кожные нарушения","53 - Нарушения веса у ребенка"],
		"ynnnny":["Капризы в еде","53 - Нарушения веса"],
		"ynny":["Детская консультация"],
		"yny":["Курение, употребление алкоголя и наркотиков у подростков"],
		"yy":["23 - Трудности в школе"]
	},
	"52":{
		"info0":["25 - Пятна и высыпания у детей", "76 - Общие кожные нарушения"],
		"info1":["Угри у подростков"],
		"info2":["Комедоны"],
		"ynn":["Угри у подростков"],
		"yny":["Угри у подростков"],
		"yy":["Угри у подростков"]
	},
	"53":{
		"info0":["Показатели физического развития детей", "11 - Чрезмерная прибавка в весе у ребенка"],
		"nn":["Показатели физического развития детей"],
		"nynn":["Нервная анорексия","51 - Проблемы поведения"],
		"nyny":["Нервная анорексия и булимия"],
		"nyyy":["Составные части рационального питания"],
		"y":["11 - Чрезмерная прибавка в весе"]
	},
	"54":{
		"info0":["55 - Утомляемость","58 - Нарушения сна"],
		"nnny":["55 - Утомляемость"],
		"nny":["59 - Высокая температура"],
		"ny":["56 - Потеря в весе"],
		"y":["Методы расслабления","73 - Беспокойство"]
	},
	"55":{
		"info0":["58 - Нарушения сна","72 - Угнетенное состояние"],
		"nnn":["Действие алкоголя"],
		"nnnnny":["Методы расслабления"],
		"nnnny":["72 - Угнетенное состояние"],
		"nnny":["Действие алкоголя"],
		"nny":["Анализ крови"],
		"y":["58 - Нарушения сна"]
	},
	"56":{
		"info0":["Признаки потери веса","Потеря веса при беременности"],
		"info2":["Анализ крови","Ультразвуковое исследование(УЗИ)"],
		"info3":["57 - Излишний вес"],
		"nnny":["72 - Угнетенное состояние"],
		"nny":["Рентгенография грудной клетки"],
		"ny":["Анализ крови","Рентгенологическое исследование с барием", "Колоноскопия"],
		"yny":["Анализ крови"],
		"yy":["Анализ крови","Радиоизотопное сканирование"]
	},
	"57":{
		"info0":["53 - Нарушения веса у подростка","Номограммы веса тела у взрослых"],
		"nnnnnnnn":["Как похудеть"],
		"nnnnnnny":["Как похудеть"],
		"nnnny":["Как похудеть"],
		"nny":["Как похудеть"],
		"ny":["Как похудеть"],
		"yn":["Как похудеть"],
		"yy":["Как похудеть"]
	},
	"58":{
		"info0":["12 - Нарушения сна у ребенка", "73 - Беспокойство"],
		"info3":["Предупреждение боли в спине"],
		"nnnnnnny":["Ваше здоровье и физические упражнения"],
		"nnnnnny":["Снотворные препараты","Профилактика бессоницы"],
		"nnnny":["Кофеин"],
		"nnny":["Профилактика бессоницы"],
		"nynnnnnny":["Ваше здоровье и физические упражнения"],
		"nynnnnny":["Снотворные препараты","Профилактика бессоницы"],
		"nynnny":["Кофеин"],
		"nynny":["Профилактика бессоницы"],
		"nyy":["72 - Угнетенное состояние"],
		"ynnnnnnny":["Ваше здоровье и физические упражнения"],
		"ynnnnnny":["Снотворные препараты","Профилактика бессоницы"],
		"ynnnny":["Кофеин"],
		"ynnny":["Профилактика бессоницы"],
		"ynynnnnnny":["Ваше здоровье и физические упражнения"],
		"ynynnnnny":["Снотворные препараты","Профилактика бессоницы"],
		"ynynnny":["Кофеин"],
		"ynynny":["Профилактика бессоницы"],
		"ynyy":["72 - Угнетенное состояние"],
		"yy":["73 - Беспокойство"]
	},
	"59":{
		"info0":["14 - Высокая температура у ребенка", "89 - Кашель"],
		"nnnnnnyny":["Влагалищное исследование"],
		"nnnnnnyy":["146 - Трудности грудного вскармливания"],
		"nnnny":["Внутривенная пиелография","132 - Болезненное мочеиспускание у женщин",'133 - Учащенное мочеиспускание',"104 - Расстройства мочеиспускания","117 - Болезненное мочеиспускание у мужчин"],
		"nnny":["Анализ крови"],
		"nny":["86 - Боль в горле"],
		"nynnnnnnyny":["Влагалищное исследование"],
		"nynnnnnnyy":["146 - Трудности грудного вскармливания"],
		"nynnnny":["Внутривенная пиелография","132 - Болезненное мочеиспускание у женщин",'133 - Учащенное мочеиспускание',"104 - Расстройства мочеиспускания","117 - Болезненное мочеиспускание у мужчин"],
		"nynnny":["Анализ крови"],
		"nynny":["86 - Боль в горле"],
		"nyny":["Как снизить температуру","85 - Насморк","86 - Боль в горле"],
		"nyy":["Люмбальная пункция","64 - Головная боль","94 - Рвота","69 - Забывчивость и помрачение сознания"],
		"ynnnnnnnyny":["Влагалищное исследование"],
		"ynnnnnnnyy":["146 - Трудности грудного вскармливания"],
		"ynnnnny":["Внутривенная пиелография","132 - Болезненное мочеиспускание у женщин",'133 - Учащенное мочеиспускание',"104 - Расстройства мочеиспускания","117 - Болезненное мочеиспускание у мужчин"],
		"ynnnny":["Анализ крови"],
		"ynnny":["86 - Боль в горле"],
		"ynny":["Как снизить температуру"],
		"yy":["Как снизить температуру","Рентгенография грудной клетки"]
	},
	"60":{
		"info0":["57 - Излишний вес"],
		"info1":["Потовые железы"],
		"info2":["Запах тела"],
		"nnnnnnnny":["Потовые железы","Запах тела"],
		"nnnnnnny":["73 - Беспокойство"],
		"nnnnnny":["Потовые железы"],
		"nnnny":["Действие алкоголя"],
		"nny":["59 - Высокая температура"],
		"nynnnnnnny":["Потовые железы","Запах тела"],
		"nynnnnnny":["73 - Беспокойство"],
		"nynnnnny":["Потовые железы"],
		"nynnny":["Действие алкоголя"],
		"nyny":["59 - Высокая температура"],
		"nyy":["Менопауза"],
		"y":["Номограммы веса тела у взрослых"],
		"ynnnnnnnnnny":["Потовые железы","Запах тела"],
		"ynnnnnnnnny":["73 - Беспокойство"],
		"ynnnnnnnny":["Потовые железы"],
		"ynnnnnny":["Действие алкоголя"],
		"ynnnny.png":["59 - Высокая температура"],
		"ynnnynnnnnnny":["Потовые железы","Запах тела"],
		"ynnnynnnnnny":["73 - Беспокойство"],
		"ynnnynnnnny":["Потовые железы"],
		"ynnnynnny":["Действие алкоголя"],
		"ynnnyny":["59 - Высокая температура"],
		"ynnnyy":["Менопауза"],
		"ynnynnnnnnnny":["Потовые железы","Запах тела"],
		"ynnynnnnnnny":["73 - Беспокойство"],
		"ynnynnnnnny":["Потовые железы"],
		"ynnynnnny":["Действие алкоголя"],
		"ynnynny":["59 - Высокая температура"],
		"ynnyny":["Менопауза"],
		"ynnyy":["Анализ крови","Рентгенография грудной клетки"],
		"yny":["Анализ крови","Радиоизотопное сканирование"],
		"yy":["57 - Излишний вес"]
	},
	"61":{
		"info0":["16 - Кожный зуд у ребенка"],
		"nnnny":["Анализ крови","Ультразвуковое исследование(УЗИ)"],
		"nnny":["130 - Раздражение половых органов"],
		"y":["77 - Пятна и высыпания"]
	},
	"62":{
		"info0":["124 - Заболевания молочных желез у женщин","115 - Боль и опухание яичек у мужчин","78 - прыщи и уплотнения на коже"],
		"info1":["Эндоскопия"],
		"nnnnyy":["86 - Боль в горле"],
		"nnnnyny":["79 - С температурой"],
		"nny":["Анализ крови"],
		"ny":["Что такое грыжа?"]
	},
	"63":{
		"info0":["17 - Обмороки, приступы головокружения и судороги у ребенка"],
		"nnnnnnnnnny":["Эндоскопия","Рентгенологическое исследование с барием","Биопсия"],
		"nnnnnnnnnyny":["Эндоскопия","Рентгенологическое исследование с барием","Биопсия"],
		"nnnnnnnnnyy":["Рентгенологическое исследование костей"],
		"nnnnnnny":["Электрокардиография(ЭКГ)"],
		"nnnnnnyn":["Компьютерная томография(КТ)"],
		"nnnnnnyy":["Кровоснабжение мозга","Электрокардиография(ЭКГ)","Рентгенография грудной клетки","Ангиография","Ишемическая болезнь сердца(ИБС)"],
		"nnnnny":["Как снизить температуру"],
		"y":["65 - Головокружение"]
	},
	"64":{
		"info0":["18 - Головная боль у ребенка"],
		"nnnnnny":["136 - Выборы способа предохранения для женщин"],
		"nnnnny":["73 - Беспокойство","72 - Угнетенное состояние"],
		"nnnny":["Напряжение глаз","Проверка зрения"],
		"nnny":["85 - Насморк"],
		"nnyn":["94 - Рвота"],
		"nnyynnn":["94 - Рвота"],
		"nnyynny":["Как уменьшить головную боль","94 - Рвота"],
		"ny":["Компьютерная томография(КТ)"],
		"y":["59 - Высокая температура"]
	},
	"65":{
		"info0":["17 - Обмороки, приступы головокружения и судороги у ребенка"],
		"nny":["Как сохраняется равновесие"],
		"ny":["Как сохраняется равновесие"],
		"yn":["Компьютерная томография(КТ)"],
		"yy":["Кровоснабжение мозга","Электрокардиография(ЭКГ)","Рентгенография грудной клетки","Ангиография","Ишемическая болезнь сердца(ИБС)"]
	},
	"66":{
		"nnyyn":["Компьютерная томография"],
		"nnyyy":["Кровоснабжение мозга","Электрокардиография(ЭКГ)","Рентгенография грудной клетки","Ангиография","Ишемическая болезнь сердца(ИБС)"],
		"nynnyyn":["Компьютерная томография"],
		"nynnyyy":["Кровоснабжение мозга","Электрокардиография(ЭКГ)","Рентгенография грудной клетки","Ангиография","Ишемическая болезнь сердца(ИБС)"]
	},
	"67":{
		"info0":["17 - Обмороки, приступы головокружения и судороги у ребенка"],
		"nynnny":["Анализ крови","Радиоизотопное сканирование"],
		"nynny":["Кофеин"],
		"nyny":["Действие алкоголя"]
	},
	"68":{
		"nnyy":["Как уменьшить головную боль"],
		"ny":["80 - Боль и раздражение глаза"]
	},
	"69":{
		"info0":["20 - Помрачение сознания у ребенка"],
		"nnnnny":["Психотерапия"],
		"nnny":["Действие алкоголя"],
		"ynnnnnnny":["Психотерапия"],
		"ynnnnny":["Действие алкоголя"],
		"ynny":["Как снизить температуру","59 - Высокая температура"],
		"ynyn":["Компьютерная томография(КТ)"],
		"ynyy":["Кровоснабжение мозга","Электрокардиография(ЭКГ)","Рентгенография грудной клетки","Ангиография","Ультразвуковое исследование(УЗИ)","Ишемическая болезнь сердца(ИБС)"],
		"yy":["Компьютерная томография(КТ)"]
	},
	"70":{
		"info0":["21 - Нарушения речи у ребенка"],
		"nny":["Действие алкоголя"],
		"ny":["93 - Заболевания слизистой рта и языка"],
		"yn":["Компьютерная томография(КТ)"],
		"yy":["Кровоснабжение мозга","Электрокардиография(ЭКГ)","Рентгенография грудной клетки","Ангиография","Ультразвуковое исследование(УЗИ)","Ишемическая болезнь сердца(ИБС)"]
	},
	"71":{
		"nnnny":["Что такое стресс?"],
		"nnny":["Психотерапия"],
		"nnyy":["Сексуальная ориентация у мужчин","Сексуальная ориентация у женщин"],
		"ny":["73 - Беспокойство"],
		"y":["72 - Угнетенное состояние"]
	},
	"72":{
		"info0":["147 - Угнетенное состояние после родов"],
		"nnnnnnnny":["Менопауза","Ваше здоровье и физические упражнения"],
		"nnnnnnny":["Действие алкоголя"],
		"nnnnny":["Менструальный цикл","Лечение менструальных состояний","127 - Болезненные менструации"],
		"nnnny":["147 - Угнетенное состояние после родов"],
		"nnny":["Что такое стресс?","73 - Беспокойство"],
		"y":["58 - Нарушения сна","55 - Утомляемость","64 - Головная боль","135 - Снижение полового влечения у женщин","54 - Плохое самочувствие"],
	},
	"73":{
		"info1":["с.177 - Методы расслабления при приступе паники"],
		"info2":["Спастический колит"],
		"info3":["Что такое стресс?","Профилактика бессоницы"],
		"nny":["Психотерапия"],
		"ny":["Психотерапия"],
		"ynnnnny":["Психотерапия"],
		"ynnnny":["Психотерапия"],
		"ynnny":["Сексуальная ориентация у мужчин","Сексуальная ориентация у женщин","Беседа с сексологом","Специфические проблемы мужчин","Специфические проблемы женщин"],
		"ynny":["Анализ крови","Радиоизотопное сканирование"],
		"yny":["Что такое стресс?"],
		"yy":["Психотерапия"]
	},
	"74":{
		"info0":["24 - Заболевания волос, кожи головы и уход за ногтями у ребенка"],
		"nny":["Экзема"],
		"ynnnnnny":["Экзема"],
		"ynnnny":["Уход за волосами"],
		"ynnny":["Менопауза","Уход за волосами"]
	},
	"75":{
		'nnnn':['Уход за ногтями'],
		'nnny':['Уход за ногтями'],
		"yy":["111 - Заболевания стоп", "Уход за ногтями"],
	},
	"76":{
		"info0":["4 - Кожные нарушения у младенца до года","52 - Кожные нарушения у подростка"],
		"info1":["Строение кожи"],
		"nnnnnnnyy":["139 - Изменения кожи при беременности"],
		"nnnnnny":["Биопсия"],
		"nnny":["77 - Пятна и высыпания"],
		"nny":["61 - Кожный зуд"],
		"ny":["78 - Прыщи и уплотнения на коже"],
		"yn":["77 - Пятна и высыпания"],
		"yy":["79 - Сыпь с температурой"]
	},
	"77":{
		"info0":["25 - Пятна и высыпания у ребенка"],
		"info1":["Потовые железы"],
		"info2":["Строение кожи"],
		"info3":["Строение кожи"],
		"nnnnyy":["61 - Кожный зуд"],
		"nyyyn":["Строение кожи","Экзема"],
		"nyyyy":["Экзема"],
		"y":["79 - Сыпь с температурой"]
	},
	"78":{
		"info0":["62 - Припухлости и уплотнения под кожей"],
		"ny":["Биопсия"],
		"yn":["Биопсия"],
		"yy":["Биопсия"]
	},
	"79":{
		"info0":["26 - Сыпь с температурой у ребенка"],
		"nnnyn":["Анализ крови","Люмбальная пункция"],
		"nnnyy":["Люмбальная пункция","94 - Рвота","64 - Головная боль"],
		"nny":["Краснуха и беременность"],
		"nynyn":["Анализ крови","Люмбальная пункция"],
		"nynyy":["Люмбальная пункция","94 - Рвота","64 - Головная боль"],
		"nyy":["85 - Насморк","89 - Кашель","80 - Боль и раздражение глаза"],
	},
	"80":{
		"info0":["27 - Глазные заболевания у ребенка"],
		"info2":["Проверка зрения"],
		"nnnny":["Перхоть"],
		"ny":["Первая помощь при травмах глаза"],
		"y":["Первая помощь при травмах глаза"]
	},
	"81":{
		"info0":["28 - Нарушения и ухудшение зрения у ребенка"],
		"nnnyy":["Как уменьшить головную боль","64 - Головная боль"],
		"nnyn":["Компьютерная томография(КТ)"],
		"nyy":["80 - Боль и раздражение глаза"]
	},
	"82":{
		"info0":["29 - Боль и раздражение в ухе у ребенка"],
		"nnny":["Как лечить простуду","85 - Насморк"],
	},
	"83":{
		"info1":["Как сохраняется равновесие"],
		"nnny":["Первая помощь при попадании насекомого в ухо"],
		"ny":["84 - Глухота"],
	},
	"84":{
		"info0":["30 - Глухота у ребенка"],
		"nnnnnnyyn":["Глухота и беременность"],
		"nnny":["Как сохраняется равновесие","65 - Головокружение"],
		"nnynnnnyyn":["Глухота и беременность"],
		"nnyny":["Как сохраняется равновесие","65 - Головокружение"],
		"y":["82 - Боль в ухе"]
	},
	"85":{
		"info0":["31 - Насморк у ребенка"],
		"nyn":["Как лечить простуду"],
		"ynyn":["86 - Боль в горле"],
		"ynyy":["Как лечить простуду"],
	},
	"86":{
		"info0":["32 - Боль в горле у ребенка"],
		"nnnny":["87 - Охриплость и потеря голоса"],
		"nny":["Как лечить простуду"],
		"nyn":["Как облегчить боль в горле"],
		"nyy":["Эпидемический паротит и бесплодие"],
		"ynnnny":["87 - Охриплость и потеря голоса"],
		"ynny":["Как лечить простуду"],
		"ynyn":["Как облегчить боль в горле"],
		"ynyy":["Эпидемический паротит и бесплодие"],
		"yy":["64 - Головная боль","89 - Кашель","54 - Плохое самочувствие"]
	},
	"87":{
		"nnnyn":["Биопсия"],
		"nnnyy":["54 - Плохое самочувствие","55 - Утомляемость"],
		"nny":["Последствия курения","Действие алкоголя"],
		"ynn":["Лечение ларингита"],
		"yny":["Лечение ларингита"],
		"yy":["Лечение ларингита","85 - Насморк","89 - Кашель","86 - Боль в горле"],
	},
	"88":{
		"info0":["35 - Шумное дыхание у ребенка"],
		"nnyy":["Рентгенография грудной клетки"],
		"ny":["59 - Высокая температура"],
	},
	"89":{
		"info0":["33 - Кашель у ребенка"],
		"nnnny":["Бронхоскопия","Рентгенография грудной клетки"],
		"nny":["90 - Затрудненное дыхание"],
		"nynnnny":["Бронхоскопия","Рентгенография грудной клетки"],
		"nynny":["90 - Затрудненное дыхание"],
		"nyny":["Как лечить простуду"],
		"nyyn":["59 - Высокая температура"],
		"nyyy":["59 - Высокая температура"],
		"ynnnnnnny":["Бронхоскопия","Рентгенография грудной клетки"],
		"ynnnnny":["90 - Затрудненное дыхание"],
		"ynnnnynnnny":["Бронхоскопия","Рентгенография грудной клетки"],
		"ynnnnynny":["90 - Затрудненное дыхание"],
		"ynnnnyny":["Как лечить простуду"],
		"ynnnnyyn":["59 - Высокая температура"],
		"ynnnnyyy":["59 - Высокая температура"],
		"ynnny":["Рентгенография грудной клетки","Бронхоскопия"],
		"yy":["87 - Охриплость и потеря голоса"]
	},
	"90":{
		"info0":["Первая помощь при удушье"],
		"info1":["Первая помощь при удушье"],
		"info2":["Дыхание рот-в-рот и рот-в-нос"],
		"nnnnny":["143 - Одышка при беременности"],
		"nnnny":["Рентгенография грудной клетки"],
		"nnnyn":["Рентгенография грудной клетки"],
		"nnnyy":["Рентгенография грудной клетки"],
		"nnynnny":["Приступы паники"],
		"nnynny":["Рентгенография грудной клетки","Радиоизотопное сканирование","Электрокардиография(ЭКГ)"],
		"ny":["88 - Свистящее дыхание"],
		"y":["106 - Боль в груди"]
	},
	"91":{
		"info0":["36 - Зубная боль у ребенка"],
		"nnnnn":["Уход за зубами"],
		"nnyy":["Уход за зубами"],
		"ny":["Уход за зубами"],
	},
	"92":{
		"info1":["Бронхоскопия"],
		"nny":["73 - Беспокойство"],
		"nynny":["73 - Беспокойство"],
		"nyny":["Рентгенологическое исследование с барием","Эндоскопия","Биопсия"],
		"nyy":["141 - Изжога при беременности","Как похудеть"],
		"yn":["86 - Боль в горле"]
	},
	"93":{
		"info0":["Уход за зубами"],
		"info2":["Уход за зубами","Уход за зубными протезами","Последствия курения"],
		"nnnynny":["Экзема"],
		"nny":["Уход за зубами"],
		"nynnnynny":["Экзема"],
		"nynny":["Уход за зубами"],
		"nynyy":["54 - Плохое самочувствие","59 - Высокая температура","Анализ крови"],
		"ynnnnynny":["Экзема"],
		"ynnny":["Уход за зубами"],
		"ynnynnnynny":["Экзема"],
		"ynnynny":["Уход за зубами"],
		"ynnynyy":["54 - Плохое самочувствие","59 - Высокая температура","Анализ крови"],
		"ynnyy":["Анализ крови"],
	},
	"94":{
		"info0":["7 - рвота у младенца до года","37 - рвота у ребенка", "95 - Повторная рвота","138 - Тошнота и рвота при беременности"],
		"nnnnnnnny":["Анализ крови","Ультразвуковое исследование(УЗИ)","Компьютерная томография(КТ)"],
		"nnnnnnny":["Проверка слуха"],
		"nnnnnny":["Лечение рвоты"],
		"nnnnny":["Лечение рвоты"],
		"nnnny":["Рекомендации при гастроэнтерите","59 - Высокая температура"],
		"nny":["64 - Головная боль"],
		"y":["95 - Повторная рвота"]
	},
	"95":{
		"info0":["94 - Рвота"],
		"nnnnnnyy":["Радиоизотопное сканирование","Компьютерная томография(КТ)"],
		"nnnnny":["Действие алкоголя","Лечение рвоты"],
		"nnnny":["Рентгенологическое исследование с барием","Эндоскопия"],
		"nnny":["Анализ крови","Ультразвуковое исследование(УЗИ)","Компьютерная томография(КТ)"],
		"nnynnnnnyy":["Радиоизотопное сканирование","Компьютерная томография(КТ)"],
		"nnynnnny":["Действие алкоголя","Лечение рвоты"],
		"nnynnny":["Рентгенологическое исследование с барием","Эндоскопия"],
		"nnynny":["Анализ крови","Ультразвуковое исследование(УЗИ)","Компьютерная томография(КТ)"],
		"nnyny":["Холецистография","Ультразвуковое исследование(УЗИ)","Удаление желчного пузыря"],
		"nnyy":["Эндоскопия","Рентгенологическое исследование с барием"],
		"ny":["141 - Изжога при беременности","Как похудеть"],
		"y":["138 - Тошнота и рвота при беременности"]
	},
	"96":{
		"info0":["38 - Боли в животе у ребенка","97 - Повторные боли в животе"],
		"nnnnnnyy":["106 - Боль в груди"],
		"nnnnny":["Холецистография","Ультразвуковое исследование(УЗИ)","Удаление желчного пузыря"],
		"nnnnynnnnyy":["106 - Боль в груди"],
		"nnnnynnny":["Холецистография","Ультразвуковое исследование(УЗИ)","Удаление желчного пузыря"],
		"nnnnynny":["117 - Болезненное мочеиспускание у мужчин","132 - Болезненное мочеиспускание у женщин","133 - Учащенное мочеиспускание"],
		"nnnnynyy":["127 - Болезненные менструации"],
		"nnnnyynnnnnyy":["106 - Боль в груди"],
		"nnnnyynnnny":["Холецистография","Ультразвуковое исследование(УЗИ)","Удаление желчного пузыря"],
		"nnnnyynnny":["117 - Болезненное мочеиспускание у мужчин","132 - Болезненное мочеиспускание у женщин","133 - Учащенное мочеиспускание"],
		"nnnnyynny":["Влагалищное исследование"],
		"nnnnyynyy":["127 - Болезненные менструации"],
		"nnnnyyy":["Выкидыш"],
		"nnny":["Внутривенная пиелография"],
		"nny":["Рекомендации при гастроэнтерите"],
		"y":["97 - Повторные боли в животе"]
	},
	"97":{
		"info0":["96 - Боли в животе"],
		"nnyny":["145 - Начались ли роды?"],
		"nnyy":["Влагалищное исследование"],
		"nynnyny":["145 - Начались ли роды?"],
		"nynnyy":["Влагалищное исследование"],
		"nynyn":["Рентгенологическое исследование с барием","Колоноскопия"],
		"nynyy":["Спастический колит","Рентгенологическое исследование с барием","Эндоскопия","Преимущества диеты с большим содержанием клетчатки"],
		"nyy":["Что такое грыжа?"],
		"ynnnnnyny":["145 - Начались ли роды?"],
		"ynnnnnyy":["Влагалищное исследование"],
		"ynnnnynnyny":["145 - Начались ли роды?"],
		"ynnnnynnyy":["Влагалищное исследование"],
		"ynnnnynyn":["Рентгенологическое исследование с барием","Колоноскопия"],
		"ynnnnynyy":["Спастический колит","Рентгенологическое исследование с барием","Эндоскопия","Преимущества диеты с большим содержанием клетчатки"],
		"ynnnnyy":["Что такое грыжа?"],
		"ynnny":["Рентгенологическое исследование с барием","Эндоскопия"],
		"ynny":["Ультразвуковое исследование(УЗИ)","Удаление желчного пузыря"],
		"yny":["Рентгенологическое исследование с барием","Эндоскопия"],
		"yy":["Как похудеть"]
	},
	"98":{
		"nnnnnn":["Номограммы веса тела у взрослых"],
		"nnnnnny":["Как похудеть"],
		"nnnnny":["Увеличение предстательной железы"],
		"nnnny":["Анализ крови","Электрокардиография(ЭКГ)","Внутривенная пиелография"],
		"nnny":["101 - Запоры"],
		"nny":["Как похудеть"],
		"ny":["Установление беременности"],
		"yn":["99 - газы"],
		"yyy":["99 - Газы"]
	},
	"99":{
		"nnny":["Анализ крови"],
		"nny":["Рентгенологическое исследование с барием","Эндоскопия","Преимущества диеты с большим содержанием клетчатки"],
		"yny":["Как похудеть"],
		"yy":["138 - Тошнота и рвота при беременности","141 - Изжога при беременности"],
	},
	"100":{
		"info0":["8 - понос у младенца до года","40 - понос у ребенка", "136 - Выбор способа предохранения для женщин"],
		"nnny":["Рекомендации при гастроэнтерите"],
		"nny":["Рекомендации при гастроэнтерите"],
		"ny":["Понос путешественника","Рентгенологическое исследование с барием","Колоноскопия"],
		"ynn":["Рентгенологическое исследование с барием","Колоноскопия"],
		"yny":["97 - Повторные боли в животе"],
		"yy":["Спастический колит","Рентгенологическое исследование с барием","Колоноскопия","Преимущества диеты с большим содержанием клетчатки"],
	},
	"101":{
		"info0":["41 - запор у ребенка"],
		"nnnnn":["Преимущества диеты с большим содержанием клетчатки"],
		"nnnny":["Преимущества диеты с большим содержанием клетчатки"],
		"nnnynn":["Преимущества диеты с большим содержанием клетчатки"],
		"nnnyny":["Преимущества диеты с большим содержанием клетчатки"],
		"nnnyy":["Рентгенологическое исследование с барием","Колоноскопия"],
		"ny":["Преимущества диеты с большим содержанием клетчатки"],
		"ynn":["Преимущества диеты с большим содержанием клетчатки"],
		"yny":["Преимущества диеты с большим содержанием клетчатки"],
		"yy":["Преимущества диеты с большим содержанием клетчатки"],
	},
	"102":{
		"info0":["42 - необычный вид кала у ребенка"],
		"nnn":["103 - Заболевания заднего прохода"],
		"nnyn":["103 - Заболевания заднего прохода"],
		"nyn":["Эндоскопия","Рентгенологическое исследование с барием","Биопсия"],
		"yn":["Лечение геморроя","Колоноскопия","Рентгенологическое исследование с барием","103 - Заболевания заднего прохода"],
		"yy":["Понос путешественника","Рентгенологическое исследование с барием","Колоноскопия"],
	},
	"103":{
		"info1":["Преимущества диеты с большим содержанием клетчатки"],
		"nnyn":["61 - Кожный зуд"],
		"ny":["Преимущества диеты с большим содержанием клетчатки","Лечение геморроя"],
		"y":["Лечение геморроя","Колоноскопия","Рентгенологическое исследование с барием"],
	},
	"104":{
		"info0":["43 - Нарушения мочеиспускания у ребенка","117 - Болезненное мочеиспускание у мужчин","132 - Болезненное мочеиспускание у женщин"],
		"nnny":["131 - Непроизвольное мочеиспускание у женщин","Увеличение предстательной железы"],
		"nny":["131 - Непроизвольное мочеиспускание у женщин","Увеличение предстательной железы"],
		"nyn":["Анализ крови","Внутривенная пиелография"],
		"nyy":["Анализ крови"],
		"y":["117 - Болезненное мочеиспускание у мужчин","132 - Болезненное мочеиспускание у женщин"]
	},
	"105":{
		"nnnnny":["Электрокардиография(ЭКГ)","Рентгенография грудной клетки"],
		"nnnny":["Анализ крови", "126 - Обильные менструации"],
		"nnny":["Анализ крови","Радиоизотопное сканирование"],
		"nny":["Последствия курения"],
		"ny":["73 - Беспокойство"],
		"y":["Кофеин"]
	},
	"106":{
		"nnnnnyny":["Рентгенография грудной клетки"],
		"nnnnnyy":["Рентгенография грудной клетки"],
		"nnny":["141 - изжога при беременности","Как похудеть"],
		"nynn":["Рентгенография грудной клетки"],
		"nyny":["89 - Кашель","59 - Высокая температура"],
		"nyy":["Рентгенография грудной клетки","Радиоизотопное сканирование","Электрокардиография(ЭКГ)"],
		"ynnn":["Ишемическая болезнь сердца(ИБС)","Электрокардиография(ЭКГ)","Рентгенография грудной клетки","Ишемическая болезнь сердца(ИБС)"],
		"ynny":["Ишемическая болезнь сердца(ИБС)"],
		"yny":["Ишемическая болезнь сердца(ИБС)"],
		"yy":["Ишемическая болезнь сердца(ИБС)"],
	},
	"107":{
		"info0":["140 - Боль в спине при беременности"],
		"nnnnny":["140 - Боль в спине при беременности"],
		"nnnny":["Рентгенологическое исследование костей"],
		"nnnyn":["Анализ крови","Рентгенологическое исследование костей"],
		"nnnyyn":["Рентгенологическое исследование костей","Анализ крови","Как похудеть"],
		"nnnyyy":["Рентгенологическое исследование костей"],
		"nnyn":["Рекомендации при болях в спине"],
		"nnyy":["Рекомендации при болях в спине"],
		"ny":["Внутривенная пиелография"],
		"yy":["Рентгенологическое исследование костей"],
	},
	"108":{
		"nnny":["Рентгенологическое исследование костей"],
		"nny":["Рентгенологическое исследование костей"],
		"ny":["Люмбальная пункция","Компьютерная томография(КТ)"],
		"yy":["Рентгенологическое исследование костей"]
	},
	"109":{
		"info0":["45 - Боль в руке или в ноге у ребенка"],
		"nnnny":["112 - Боли и опухание суставов"],
		"nny":["Выпадение диска","Шейный спондилез","Стенокардия"],
		"yn":["Первая помощь при растяжениях","Ваше здоровье и физические упражнения"],
		"yy":["Первая помощь при подозрении на перелом кости или вывих в суставе"],
	},
	"110":{
		"info0":["45 - Боль в руке или в ноге у ребенка"],
		"info3":["Ангиография"],
		"nnnnnny":["Менопауза","Ангиография","136 - Выбор способа предохранения для женщин"],
		"nnnnny":["Анализ крови"],
		"nnnny":["Ваше здоровье и физические упражнения"],
		"nnnyy":["Ангиография","Электрокардиография(ЭКГ)","Анализ крови","Ишемическая болезнь сердца(ИБС)"],
		"nny":["112 - Боль и опухание суставов"],
		"ny":["113 - Боль в колене"],
		"yn":["Первая помощь при растяжениях"],
		"yy":["Первая помощь при подозрении на перелом кости или вывих в суставе","Рентгенологическое исследование костей"]
	},
	"111":{
		"info0":["47 - Заболевания стоп у ребенка","Уход за стопами"],
		"nnnnnnny":["Уход за стопами"],
		"nnnnnny":["Подагра","112 - Боли и опухание суставов"],
		"nnnnnynny":["Уход за стопами"],
		"nnnnnyny":["Подагра","112 - Боли и опухание суставов"],
		"nnnnynnnny":["Уход за стопами"],
		"nnnnynnny":["Подагра","112 - Боли и опухание суставов"],
		"nnnnynnynny":["Уход за стопами"],
		"nnnnynnyny":["Подагра","112 - Боли и опухание суставов"],
		"nynnnnnny":["Уход за стопами"],
		"nynnnnny":["Подагра","112 - Боли и опухание суставов"],
		"nynnnnynny":["Уход за стопами"],
		"nynnnnyny":["Подагра","112 - Боли и опухание суставов"],
		"nynnnynnnny":["Уход за стопами"],
		"nynnnynnny":["Подагра","112 - Боли и опухание суставов"],
		"nynnnynnynny":["Уход за стопами"],
		"nynnnynnyny":["Подагра","112 - Боли и опухание суставов"],
		"yn":["Первая помощь при растяжениях"],
		"yy":["Первая помощь при подозрении на перелом кости или вывих в суставе"],
	},
	"112":{
		"info0":["46 - Боли в суставах у ребенка","144 - Отечность голеностопных суставов у женщин"],
		"info2":["Первая помощь при подозрении на перелом кости или вывих в суставе"],
		"nnnnyn":["Варикозное расширение вен"],
		"nnnnyy":["144 - Отечность голеностопных суставов"],
		"nnnyy":["Анализ крови","Как похудеть"],
		"nnyn":["Анализ крови"],
		"nnyyn":["Анализ крови"],
		"nyn":["Первая помощь при растяжениях","Ваше здоровье и физические упражнения"],
		"nyy":["Первая помощь при подозрении на перелом кости или вывих в суставе"],
		"y":["113 - Боль в колене"],
	},
	"113":{
		"nnnnny":["Анализ крови","Рентгенологическое исследование костей","Как похудеть"],
		"nnnnyyy":["Анализ крови","Рентгенологическое исследование костей","Как похудеть"],
		"nny":["Подагра","112 - Боли и опухание суставов"],
		"ny":["112 - Боли и опухание суставов"],
		"yn":["Первая помощь при растяжениях","Ваше здоровье и физические упражнения"],
		"yy":["Первая помощь при подозрении на перелом кости или вывих в суставе","Рентгенологическое исследование костей"],
	},
	"114":{
		"info0":["24 - Заболевания волос, кожи головы и уход за ногтями у ребенка", "74 - Заболевания волос и кожи головы"],
		"ny":["Причины облысения у мужчин"]
	},
	"115":{
		"info0":["48 - Заболевания половых органов у мальчика"],
		"ny":["Биопсия"],
		"yny":["Эпидемический паротит и бесплодие"],
	},
	"116":{
		"info0":["48 - Заболевания половых органов у мальчика"],
		"info2":["Гигиена половых органов у мужчин"],
		"info4":["Обрезание"],
		"nnnnnny":["123 - Выборы способа предохранения для мужчин"],
		"nnnnny":["Беседа с сексологом"],
		"nnnny":["Обрезание","Гигиена половых органов у мужчин"],
		"nnny":["Венерические болезни"],
		"nny":["Венерические болезни"],
		"ny":["117 - Болезненное мочеиспускание"],
		"yn":["Обрезание"]
	},
	"117":{
		"info0":["43 - Нарушения мочеиспускания у ребенка", "104 - Расстройства мочеиспускания","132 - Болезненное мочеиспускание у женщин"],
		"info2":["Анализ крови"],
		"ny":["Венерические болезни"],
		"y":["Внутривенная пиелография"]
	},
	"118":{
		"info1":["Метод сдавливания","Снятие сексуальной тревоги"],
		"info2":["Беседа с сексологом"],
		"nnyy":["119 - Преждевременное семяизвержение","Снятие сексуальной тревоги"],
		"nyn":["Снятие сексуальной тревоги"],
		"y":["121 - Снижение полового влечения у мужчин"]
	},
	"119":{
		"info1":["Снятие сексуальной тревоги"],
		"nnny":["Снятие сексуальной тревоги","Беседа с сексологом"],
		"nny":["Метод сдавливания","Беседа с сексологом"],
		"ny":["Отсутствие сексуального опыта"],
	},
	"120":{
		"info1":["Снятие сексуальной тревоги"],
		"ynnn":["Снятие сексуальной тревоги","Рекомендации при задержке семяизвержения","Беседа с сексологом"],
		"ynny":["Половая жизнь и возраст"],
		"yny":["Рекомендации при задержке семяизвержения","Беседа с сексологом"],
		"yy":["Беседа с сексологом"]
	},
	"121":{
		"info0":["135 - Снижение полового влечения у женщин"],
		"info2":["Венерические болезни","Многочисленные половые партнеры"],
		"nnnnnnnny":["Сексуальная ориентация у мужчин"],
		"nnnnnnny":["Половая жизнь и возраст"],
		"nnnnnyn":["Беседа с сексологом"],
		"nnnnnyy":["Беседа с сексологом"],
		"nnnny":["118 - Затрудненная эрекция","119 - Преждевременное семяизвержение","120 - Замедленное семяизвержение","Беседа с сексологом"],
		"nnny":["Действие алкоголя"],
		"nny":["72 - Угнетенное состояние"],
		"ny":["55 - Утомляемость","73 - Беспокойство"],
		"y":["Беседа с сексологом"],
	},
	"122":{
		"info0":["137 - Неспособность к зачатию у женщин"],
		"info1":["Анализ спермы"],
		"info4":["Вазэктомия"],
		"nnnnnny":["Образование спермы"],
		"nnnny":["Венерические болезни","Анализ спермы"],
		"nnny":["Увеличение возможности зачатия"],
		"nny":["Анализ спермы"],
		"ny":["Эпидемический паротит и бесплодие","Анализ спермы"],
		"y":["115 - Боль и опухание яичек"],
	},
	"123":{
		"info0":["136 - Выбор способа предохранения для женщин","Способы предохранения для женщин"],
		"info1":["Образование спермы","Анализ спермы"],
		"nn":["Способы предохранения для женщин"],
	},
	"124":{
		"info0":["106 - Боль в груди", "146 - Трудности грудного вскармливания"],
		"info2":["Самообследование молочных желез"],
		"nnyny":["Установление беременности"],
		"nnyy":["Менструальный цикл","Лечение менструальных состояний"],
		"ny":["Рак молочной железы","Предменструальная болезненность молочных желез"],
		"y":["146 - Трудности грудного вскармливания"],
	},
	"125":{
		"info0":["128 - Нерегулярные выделения крови из влагалища","129 - Необычные выделения из влагалища"],
		"ynnn":["Номограммы веса тела у взрослых"],
		"ynnnnnny":["Менопауза"],
		"ynnnny":["56 - Потеря в весе"],
		"ynnny":["56 - Потеря в весе"],
		"ynny":["Менструальный цикл"],
		"yy":["Установление беременности"],
	},
	"126":{
		"info0":["127 - Болезненные менструации","128 - Нерегулярные выделения крови из влагалища"],
		"info1":["Прерывание беременности"],
		"nnnny":["Влагалищное исследование","Выскабливание матки","Гистерэктомия"],
		"nnny":["Влагалищное исследование","Выскабливание матки","Лапароскопия","Гистерэктомия"],
		"nny":["Выкидыш","127 - Болезненные менструации","128 - Нерегулярные выделения крови из влагалища"],
		"ny":["136 - Выбор способа предохранения для женщин"],
		"y":["Анализ крови","Выскабливание матки"]
	},
	"127":{
		"info0":["126 - Обильные менструации","128 - Нерегулярные выделения крови из влагалища"],
		"info1":["Менструальный цикл","c.297 - Домашняя аптечка","с.298 - Мочегонные препараты","136 - Выбор способа предохранения для женщин","Выскабливание матки"],
		"nnny":["Влагалищное исследование","Выскабливание матки","Лапароскопия","Гистерэктомия"],
		"nny":["136 - Выбор способа предохранения для женщин"],
		"ny":['Влагалищное исследование'],
		"yn":["Лечение менструальных состояний"],
		"yynny":["Влагалищное исследование","Выскабливание матки","Лапароскопия","Гистерэктомия"],
		"yyny":["136 - Выбор способа предохранения для женщин"],
		"yyy":['Влагалищное исследование'],
	},
	"128":{
		"info0":["125 - Отстутсвие менструаций","126 - Обильные менструации","129 - Необычные выделения из влагалища"],
		"info1":["Менопауза"],
		"info2":["Влагалищное исследование","Биопсия"],
		"nnnnny":["136 - Выбор способа предохранения для женщин"],
		"nnnny":["Влагалищное исследование","Исследование шейки матки","Выскабливание матки","Гистерэктомия"],
		"nnny":["Влагалищное исследование","Исследование шейки матки","Гистерэктомия"],
		"nyny":["Менопауза"],
		"y":["142 - Выделения крови из влагалища (при беременности)"]
	},
	"129":{
		"info0":["128 - Нерегулярные выделения крови из влагалища","134 - Болезненный половой акт у женщин","136 - Выбор способа предохранения для женщин"],
		"info1":["Исследование шейки матки"],
		"info2":["Влагалищное исследование"],
		"nnynn":["Влагалищное исследование", "Венерические болезни"],
		"nnyny":["Влагалищное исследование"],
		"ny":["Влагалищное исследование","136 - Выбор способа предохранения для женщин"],
		"ynn":["Менструальный цикл","Исследование шейки матки"],
		"yny":["136 - Выбор способа предохранения для женщин"],
		"yy":["130 - Раздражение половых органов"]
	},
	"130":{
		"info0":["61 - Кожный зуд", "132 - Болезненное мочеиспускание у женщин","134 - Болезненный половой акт у женщин"],
		"nnnny":["Менопауза"],
		"nnny":["Гигиена половых органов у женщин"],
		"nny":["133 - Учащенное мочеиспускание"],
		"y":["129 - Необычные выделения из влагалища"]
	},
	"131":{
		"info0":["104 - Расстройства мочеиспускания", "132 - Болезненное мочеиспускание у женщин","133 - Учащенное мочеиспускание у женщин"],
		"nny":["Исследование мочевого пузыря","Упражнения для мышц таза"],
		"nynn":["Упражнения для мышц таза","Как похудеть"],
		"nyny":["Как похудеть"],
		"nyy":["Упражнения для мышц таза","Как похудеть"],
		"y":["132 - Болезненное мочеиспускание"]
	},
	"132":{
		"info0":["104 - Расстройства мочеиспускания","130 - раздражение половых органов у женщин","133 - Учащенное мочеиспускание у женщин"],
		"nnnn":["Рекомендации при инфекционных заболеваниях мочевого пузыря и уретры"],
		"nnnyny":["Влагалищное исследование","Венерические болезни"],
		"nnnyy":["Влагалищное исследование","136 - Выбор способа предохранения для женщин"],
		"nnynnnn":["Рекомендации при инфекционных заболеваниях мочевого пузыря и уретры"],
		"nnynnnyny":["Влагалищное исследование","Венерические болезни"],
		"nnynnnyy":["Влагалищное исследование","136 - Выбор способа предохранения для женщин"],
		"nnynny":["Рекомендации при инфекционных заболеваниях мочевого пузыря и уретры"],
		"nnyny":["Рекомендации при инфекционных заболеваниях мочевого пузыря и уретры","Внутривенная пиелография","Цистоскопия"],
		"nnyy":["Рекомендации при инфекционных заболеваниях мочевого пузыря и уретры","Внутривенная пиелография","Цистоскопия"],
		"ny":["Внутривенная пиелография","Анализ крови"],
		"y":["Внутривенная пиелография","Анализ крови"],
	},
	"133":{
		"info0":["104 - Расстройства мочеиспускания","131 - Непроизвольное мочеиспускание","132 - Болезненное мочеиспускание"],
		"info2":["131 - Непроизвольное мочеиспускание у женщин","132 - Болезненное мочеиспускание у женщин","Анализ крови"],
		"nnnnny":["131 - Непроизвольное мочеиспускание у женщин"],
		"nnnny":["Исследование мочевого пузыря","Упражнения для мышц таза"],
		"nynnnnnny":["131 - Непроизвольное мочеиспускание у женщин"],
		"nynnnnny":["Исследование мочевого пузыря","Упражнения для мышц таза"],
		"nyny":["Кофеин","Действие алкоголя"],
		"nyy":["Анализ крови"],
		"y":["132 - Болезненное мочеиспускание у женщин"]
	},
	"134":{
		"info0":["130 - Раздражение половых органов у женщин","136 - Выбор способа предохранения для женщин"],
		"info1":["Менопауза","Консультация сексолога"],
		"nnnyny":["Влагалищное исследование","Исследование шейки матки","Ультразвуковое исследование(УЗИ)","Лапароскопия"],
		"nnnyy":["Влагалищное исследование","Выскабливание матки","Лапароскопия"],
		"nnyn":["Консультация сексолога","135 - Снижение полового влечения"],
		"nnyy":["Менопауза", "Половая жизнь и возраст"],
		"ny":["129 - Необычные выделения из влагалища"],
	},
	"135":{
		"info0":["72 - Угнетенное состояние","136 - Выбор способа предохранения у женщин", "147 - Угнетенное состояние после родов"],
		"info1":["Снятие сексуальной тревоги"],
		"nnnnnnnny":["Сексуальная ориентация у женщин"],
		"nnnnnnnyn":["Консультация сексолога"],
		"nnnnnnnyy":["Консультация сексолога"],
		"nnnnnny":["Консультация сексолога"],
		"nnnnny":["Способы предохранения для женщин"],
		"nnnny":["72 - Угнетенное состояние"],
		"nnny":["Что такое стресс?","73 - Беспокойство"],
		"nny":["Анализ крови"],
		"ny":["147 - Угнетенное состояние после родов"],
	},
	"136":{
		"info0":["123 - Выбор способа предохранения для мужчин","134 - Болезненный половой акт у женщин"],
		"info1":["Венерические болезни","Исследование шейки матки"],
		"info2":["Выскабливание матки"],
		"info4":["Лапароскопия"],
		"nn":["Номограммы веса тела у взрослых"],
		"nnnn":["Способы предохранения для женщин"],
		"nnny":["Способы предохранения для женщин"],
		"nnyn":["Способы предохранения для женщин"],
		"nnyyn":["Способы предохранения для женщин"],
		"nnyyy":["Способы предохранения для женщин"],
		"nyn":["Способы предохранения для женщин"],
		"nyyn":["Способы предохранения для женщин"],
		"nyyy":["Способы предохранения для женщин"],
		"ynn":["Способы предохранения для женщин"],
		"ynyn":["Способы предохранения для женщин"],
		"ynyy":["Способы предохранения для женщин"],
		"yy":["Стерилизация"]
	},
	"137":{
		"info0":["122 - Проблемы бесплодия у мужчин"],
		"info1":["Менструальный цикл"],
		"info3":["Эндоскопия","Стерилизация","Рентгенологическое исследование с барием","Ультразвуковое исследование(УЗИ)"],
		"nnnnn":["122 - Проблемы бесплодия у мужчин"],
		"nnnny":["Лапароскопия"],
		"nnny":["Лапароскопия"],
		"nny":["Анализ крови","Выскабливание матки"],
		"ny":["Увеличение возможности зачатия"],
	},
	"138":{
		"info0":["94 - Рвота","96 - Боли в животе","141 - Изжога при беременности"],
		"nn":["Как справиться с тошнотой и рвотой"],
	},
	"139":{
		"info0":["76 - Общие кожные нарушения","77 - Пятна и высыпания на коже"],
		"nnn":["76 - Общие кожные нарушения"],
		"ny":["Угри"],
	},
	"140":{
		"info0":["107 - Боль в спине","145 - Начались ли роды?"],
		"nn":["Предупреждение боли в спине"],
		"ny":["145 - Начались ли роды?"],
		"yn":["Предупреждение боли в спине"],
		"yy":["Выкидыш","128 - Нерегулярные выделения крови из влагалища"],
	},
	"141":{
		"info0":["96 - Боли в животе","138 - Тошнота и рвота при беременности"],
		"n":["Рекомендации при изжоге","Диафрагмальная грыжа"],
		"y":["Рекомендации при изжоге"],
	},
	"142":{
		"info0":["128 - Нерегулярные выделения крови из влагалища"],
		"info1":["Ультразвуковое исследование(УЗИ)","Выскабливание матки"],
		"nnn":["Выкидыш"],
		"ny":["Выкидыш"],
		"y":["145 - Начались ли роды?","Ультразвуковое исследование(УЗИ)","Стимуляция родов"],
	},
	"143":{
		"info0":["90 - Затрудненное дыхание"],
		"info1":["Потеря веса при беременности", "Преэклампсия", "Ультразвуковое исследование(УЗИ)"],
	},
	"144":{
		"info0":["112 - Боли и опухание суставов"],
		"n":["Варикозное расширение вен"],
		"ynn":["Варикозное расширение вен"],
		"yny":["Стимуляция родов"],
		"yy":["Стимуляция родов"],
	},
	"145":{
		"nnny":["Разрыв плодного пузыря"],
		"nnyy":["140 - Боль в спине при беременности"],
		"nyy":["Стимуляция родов"],
	},
	"146":{
		"info0":["124 - Заболевания молочных желез"]
	},
	"147":{
		"info0":["72 - Угнетенное состояние","73 - Беспокойство", "135 - Снижение полового влечения у женщин"],
		"nnny":["Психотерапия"],
	}
}

image_dict = {
	"Опасные симптомы у ребенка": "https://telegra.ph/Opasnye-simptomy-09-30",
	"Опасные симптомы у детей": "https://telegra.ph/Opasnye-simptomy-09-30-3",
	"Опасные симптомы при рвоте":"https://telegra.ph/Opasnye-simptomy-09-30-4",
	"Опасные симптомы при болях в животе": "https://telegra.ph/Opasnye-simptomy-09-30-5",
	"Опасные симптомы при поносе": "https://telegra.ph/Opasnye-simptomy-09-30-6",
	"Показатели физического развития детей":"https://telegra.ph/Pokazateli-fizicheskogo-razvitiya-detej-09-29",
	"Варианты роста в грудном возрасте":"https://telegra.ph/Varianty-rosta-v-grudnom-vozraste-09-29",
	"Взвешивание и измерение младенцев и детей": "https://telegra.ph/Vzveshivanie-i-izmerenie-mladencev-i-detej-09-29",
	"Грудное и искусственное вскармливание": "https://telegra.ph/Grudnoe-i-iskusstvennoe-vskarmlivanie-09-29",	
	"Как улучшить сон ребенка": "https://telegra.ph/Kak-uluchshit-son-rebenka-09-29",
	"Периоды сна и бодрствования ребенка":"https://telegra.ph/Periody-sna-i-bodrstvovaniya-09-29",
	"Голод":"golod.png",
	"Разрыв плодного пузыря":"razriv.png",
	"Предменструальная болезненность молочных желез":"boleznennost.png",
	"Отсутствие сексуального опыта":"otsutstvie.png",
	"Подагра": "podagra.png",
	"Стенокардия":"stenokardiya.png",
	"Выпадение диска":"vipadenie_diska.png",
	"Диафрагмальная грыжа":"diafragma.png",
	"Специфические проблемы мужчин": "https://telegra.ph/Specificheskie-problemy-muzhchin-10-20",
	"Специфические проблемы женщин": "https://telegra.ph/Specificheskie-problemy-zhenshchin-10-20",
	"Воспаление мочевыводящих путей":"vospalenie_putey.png",
	"Трещина в заднем проходе":"zadniy_prohod.png",
	"Шейный спондилез":"spondilez.png",
	"Повторные боли в животе у ребенка": "povtornie_boli.png",
	"Рекомендации при общем вирусном заболевании":"recs_orvi.png",
	"Закупорка наружного слухового прохода":"zakuporka.png",
	"Меры для лечения вирусного конъюктивита": "konjuktivit.png",
	"Перхоть у детей":"perhot_deti.png",
	"Перхоть":"perhot.png",
	"Аппендицит":"appendicit.png",
	"Раздражение кожи при опрелостях":"skin_irritation.png",
	"Экзема головы":"ekzema_golovy.png",
	"Мигрень у ребенка":"migren.png",
	"Себорейный дерматит":"seboreya.png",
	"Потеря веса у новорожденных": "https://telegra.ph/Poterya-vesa-u-novorozhdennyh-09-29-2",
	"Вирусные и бактериальные инфекции у детей": "https://telegra.ph/Virusy-i-bakterialnye-infekcii-09-29",
	"Частота дыхания у ребенка": "https://telegra.ph/Vash-rebenok-dyshit-slishkom-chasto-09-30",
	"Как лечить больное горло": "https://telegra.ph/Kak-lechit-bolnoe-gorlo-09-30",
	"Люмбальная пункция у детей": "https://telegra.ph/Lyumbalnaya-punkciya-u-detej-09-29",
	"Лечение диспепсии у младенцев": "https://telegra.ph/Lechenie-dispepsii-u-mladencev-09-29",
	"Упорная рвота" : "https://telegra.ph/Upornaya-rvota-09-29",
	"Сравнительная характеристика детских инфекций": "https://telegra.ph/Sravnitelnaya-harakteristika-detskih-infekcij-09-30",
	"Уход за кожей младенца": "https://telegra.ph/Uhod-za-kozhej-mladenca-09-29",
	"Как снизить у ребенка температуру" : "https://telegra.ph/Kak-snizit-u-rebenka-temperaturu-09-29",
	"Заглатывание воздуха" : "https://telegra.ph/Zaglatyvanie-vozduha-09-29",
	"Частота кормлений и дополнительное питье" : "https://telegra.ph/CHastota-kormlenij-i-dopolnitelnoe-pite-09-29",
	"Составные части рационального питания" : "https://telegra.ph/Sostavnye-chasti-racionalnogo-pitaniya-09-30",
	"Отнятие от груди" : "https://telegra.ph/Otnyatie-ot-grudi-09-29",
	"Предостережение": "https://telegra.ph/Upornaya-rvota-09-29",
	"Плохое самочувствие у детей до двух лет" : "https://telegra.ph/Deti-do-dvuh-let-plohoe-samochuvstvie-09-29",
	"Осмотр ушей у ребенка" : "https://telegra.ph/Osmotr-ushej-09-30",
	"Как помочь вашему ребенку похудеть" : "https://telegra.ph/Kak-pomoch-vashemu-rebenku-pohudet-09-29",
	"Причины чрезмерной прибавки в весе" : "https://telegra.ph/Prichiny-chrezmernoj-pribavki-v-vese-09-29",
	"Предупреждение и преодоление нарушений сна" : "https://telegra.ph/Preduprezhdenie-i-preodolenie-narushenij-sna-09-29",
	"Курение, употребление алкоголя и наркотиков у подростков": "https://telegra.ph/Kurenie-upotreblenie-alkogolya-i-narkotiki-09-30",
	"Компьютерная томография черепа ребенка(КТ)" : "https://telegra.ph/Kompyuternaya-tomografiya-09-29",
	"Первая помощь при отравлениях" : "https://telegra.ph/Otravleniya-10-08",
	"Как измерить температуру у ребенка" : "https://telegra.ph/Kak-izmerit-temperaturu-rebenku-09-29",
	"Как измерить температуру у младенца" : "https://telegra.ph/Kak-izmerit-temperaturu-u-mladenca-09-29",
	"Как собрать среднюю порцию мочи у ребенка" : "https://telegra.ph/Kak-sobrat-srednyuyu-porciyu-mochi-09-30",
	"Лечение гастроэнтерита у детей" : "https://telegra.ph/Lechenie-gastroehnterita-u-detej-09-30",
	"Как облегчить ушную боль у ребенка" : "https://telegra.ph/Kak-oblegchit-ushnuyu-bol-u-rebenka-09-30",
	"Лимфатические железы" : "https://telegra.ph/Limfaticheskie-zhelezy-09-29",
	"Бородавки и фурункулы" : "https://telegra.ph/Borodavki-i-furunkuly-09-29",
	"Тонзиллэктомия(удаление миндалин)": "https://telegra.ph/Tonzillehktomiya-09-30",
	"Что такое миндалины?":"https://telegra.ph/CHto-takoe-mindaliny-09-30",
	"Экзема":"https://telegra.ph/EHkzema-10-01",
	"Рекомендации при кожном зуде":"https://telegra.ph/Rekomendacii-pri-kozhnom-zude-10-01",
	"Первая помощь при обмороке у детей": "https://telegra.ph/Pervaya-pomoshch-pri-obmoroke-u-detej-09-29",
	"Эпилепсия": "https://telegra.ph/EHpilepsiya-09-29",
	"Строение уха":"https://telegra.ph/Stroenie-uha-09-30",
	"Судороги при высокой температуре":"https://telegra.ph/Sudorogi-pri-vysokoj-temperature-09-29-2",
	"Как облегчить головную боль у ребенка":"https://telegra.ph/Kak-oblegchit-golovnuyu-bol-u-rebenka-09-29",
	"Проверка зрения у ребенка" : "https://telegra.ph/Proverka-zreniya-09-30",
	"Проверка зрения":"https://telegra.ph/Proverka-zreniya-10-01",
	"Как лечить простуду у ребенка":"https://telegra.ph/Kak-lechit-prostudu-u-rebenka-09-30",
	"Как лечить простуду":"https://telegra.ph/Lechenie-prostudy-10-01",
	"Развитие навыков и ловкости рук":"https://telegra.ph/Razvitie-navykov-i-lovkosti-ruk-09-29",
	"Помощь развитию речи у ребенка" : "https://telegra.ph/Pomoshch-razvitiyu-rechi-u-rebenka-09-29",
	"Проверка слуха у детей": "https://telegra.ph/Proverka-sluha-u-detej-09-30",
	"Проверка слуха":"https://telegra.ph/Proverka-sluha-u-vzroslyh-10-01",
	"Одаренные дети":"https://telegra.ph/Odarennye-deti-09-29",
	"Типы проблем поведения у детей":"https://telegra.ph/Tipy-problem-povedeniya-09-29",
	"Правила поведения и дисциплина" : "https://telegra.ph/Pravila-povedeniya-i-disciplina-09-29",
	"Детская консультация" : "https://telegra.ph/Detskaya-konsultaciya-09-29",
	"Гиперактивность" : "https://telegra.ph/Giperaktivnost-09-29",
	"Ужасные двухлетки" : "https://telegra.ph/Uzhasnye-dvuhletki-09-29",
	"Проблемы обучения у ребенка" : "https://telegra.ph/Problemy-obucheniya-09-29",
	"Дизлексия у детей" : "https://telegra.ph/Dizleksiya-09-29",
	"Прививки для детей" : "https://telegra.ph/Privivki-09-30",
	"Первая помощь при травмах глаза у детей" : "https://telegra.ph/Pervaya-pomoshch-pri-travmah-glaza-u-detej-09-30",
	"Первая помощь при травмах глаза" : "https://telegra.ph/Pervaya-pomoshch-pri-travmah-glaza-u-vzroslyh-10-01",
	"Косоглазие" : "https://telegra.ph/Kosoglazie-09-30",
	"Миринготомия и установка шунта" : "https://telegra.ph/Miringotomiya-i-ustanovka-shunta-09-30",
	"Удаление аденоидов" : "https://telegra.ph/Udalenie-adenoidov-09-30",
	"Первая помощь при удушье":"https://telegra.ph/OPP-Udushe-10-08",
	"Всё об астме" : "https://telegra.ph/Vsyo-ob-astme-09-30",
	"Дыхание рот-в-рот и рот-в-нос" : "https://telegra.ph/OPP-Dyhanie-rot-v-rot-i-rot-v-nos-10-08",
	"Как облегчить зубную боль у ребенка" : "https://telegra.ph/Kak-oblegchit-zubnuyu-bol-u-rebenka-09-30",
	"Другие заболевания, вызывающие зубную боль" : "https://telegra.ph/Drugie-zabolevaniya-vyzyvayushchie-zubnuyu-bol-09-30",
	"Профилактика кариеса" : "https://telegra.ph/Profilaktika-kariesa-09-30",
	"Что делать, когда у ребенка рвота" : "https://telegra.ph/CHto-delat-kogda-u-rebenka-rvota-09-30",
	"Строение мочевыделительной системы" : "https://telegra.ph/Stroenie-mochevydelitelnoj-sistemy-09-30",
	"Удаление аппендикса" : "https://telegra.ph/Udalenie-appendiksa-09-30",
	"Боль при аппендиците" : "https://telegra.ph/Bol-pri-appendicite-09-30",
	"Варианты роста в детском возрасте" : "https://telegra.ph/Varianty-rosta-v-detskom-vozraste-09-29",
	"Капризы в еде" : "https://telegra.ph/Kaprizy-v-ede-09-30",
	"Профилактика инфекции мочевыводящих путей" : "https://telegra.ph/Profilaktika-infekcii-mochevyvodyashchih-putej-10-09",
	"Как приучить ребенка к горшку" : "https://telegra.ph/Priuchenie-k-gorshku-09-30",
	"Первая помощь при кровотечениях" : "https://telegra.ph/OPP-Krovotechenie-10-08",
	"Боли, связанные с ростом" : "https://telegra.ph/Boli-svyazannye-s-rostom-09-30",
	"Первая помощь при подозрении на перелом кости или вывих у ребенка" :"https://telegra.ph/Pervaya-pomoshch-pri-podozrenii-na-perelom-kosti-ili-vyvih-09-30",
	"Первая помощь при растяжениях у ребенка" : "https://telegra.ph/Pervaya-pomoshch-pri-rastyazheniyah-09-30",
	"Первая помощь при растяжениях" : "https://telegra.ph/Pervaya-pomoshch-pri-rastyazheniyah-u-vzroslyh-10-01",
	"Первая помощь при подозрении на перелом кости или вывих в суставе" : "https://telegra.ph/Pervaya-pomoshch-pri-podozrenii-na-perelom-kosti-ili-vyvih-v-sustavah-10-01",
	"Первая помощь при потере сознания": "https://telegra.ph/OPP-Poterya-soznaniya-10-08",
	"Уход за ногтями" : "https://telegra.ph/Uhod-za-nogtyami-09-29",
	"Уход за стопами ребенка" : "https://telegra.ph/Uhod-za-stopami-rebenka-09-30",
	"Уход за стопами" : "https://telegra.ph/Uhod-za-stopami-10-01",
	"Обрезание у детей" : "https://telegra.ph/Obrezanie-09-30",
	"Обрезание" : "https://telegra.ph/Obrezanie-10-01",
	"Сужение крайней плоти у мальчика" : "https://telegra.ph/Suzhenie-krajnej-ploti-09-30",
	"Инородное тело в мочеиспускательном канале" : "https://telegra.ph/Inorodnoe-telo-v-mocheispuskatelnom-kanale-09-30",
	"Основные вехи нормального развития подростка": "https://telegra.ph/Osnovnye-vehi-razvitiya-podrostka-09-30",
	"Что делать при раздражении половых органов" : "https://telegra.ph/CHto-delat-pri-Razdrazhenii-polovyh-organov-09-30",
	"Угри у подростков" : "https://telegra.ph/Ugri-09-30",
	"Угри" : "https://telegra.ph/Ugri-10-01",
	"Комедоны" : "https://telegra.ph/Komedony-09-30",
	"Нервная анорексия":"https://telegra.ph/Poterya-appetita-i-nenormalno-povyshennyj-appetit-09-30",
	"Нервная анорексия и булимия":"https://telegra.ph/Poterya-appetita-i-nenormalno-povyshennyj-appetit-09-30",
	"Методы расслабления" : "https://telegra.ph/Metody-rasslableniya-10-01",
	"Действие алкоголя" : "https://telegra.ph/Dejstvie-alkogolya-09-30",
	"Анализ крови" : "https://telegra.ph/Analiz-krovi-09-30",
	"Признаки потери веса" : "https://telegra.ph/PRIZNAKI-POTERI-VESA-09-30",
	"Потеря веса при беременности" : "https://telegra.ph/POTERYA-VESA-PRI-BEREMENNOSTI-09-30",
	"Ультразвуковое исследование(УЗИ)": "https://telegra.ph/Ultrazvukovoe-skanirovanie-10-01",
	"Рентгенография грудной клетки" : "https://telegra.ph/Rentgenografiya-grudnoj-kletki-10-01",
	"Рентгенологическое исследование костей" : "https://telegra.ph/Rentgenologicheskoe-issledovanie-kostej-10-01",
	"Рентгенологическое исследование с барием" : "https://telegra.ph/Rentgenologicheskoe-issledovanie-s-bariem-10-01",
	"Колоноскопия" : "https://telegra.ph/Kolonoskopiya-10-01",
	"Радиоизотопное сканирование": "https://telegra.ph/RADIOIZOTOPNOE-SKANIROVANIE-10-01",
	"Номограммы веса тела у взрослых" : "https://telegra.ph/Nomogrammy-vesa-tela-u-vzroslyh-10-09",
	"Как похудеть" : "https://telegra.ph/Kak-pohudet-09-30-2",
	"Предупреждение боли в спине" : "https://telegra.ph/Preduprezhdenie-boli-v-spine-10-01",
	"Ваше здоровье и физические упражнения" : "https://telegra.ph/Vashe-zdorove-i-fizicheskie-uprazhneniya-10-08",
	"Снотворные препараты" : "https://telegra.ph/Snotvornye-preparaty-09-30",
	"Профилактика бессоницы" : "https://telegra.ph/Profilaktika-bessonnicy-09-30",
	"Кофеин" : "https://telegra.ph/Kofein-10-01",
	"Влагалищное исследование" : "https://telegra.ph/Vlagalishchnoe-issledovanie-10-01",
	"Внутривенная пиелография" : "https://telegra.ph/Vnutrivennaya-pielografiya-10-01",
	"Как снизить температуру" : "https://telegra.ph/OPP-Povyshenie-temperatury-10-08",
	"Люмбальная пункция" : "https://telegra.ph/Lyumbalnaya-punkciya-09-30",
	"Потовые железы": "https://telegra.ph/Potovye-zhelezy-09-30",
	"Запах тела" : "https://telegra.ph/Zapah-tela-09-30",
	"Менопауза" : "https://telegra.ph/Menopauza-10-01",
	"Установление беременности" : "https://telegra.ph/Ustanovlenie-beremennosti-10-01",
	"Эндоскопия" : "https://telegra.ph/EHndoskopiya-10-01",
	"Что такое грыжа?" : "https://telegra.ph/CHto-takoe-gryzha-10-01",
	"Биопсия" : "https://telegra.ph/Biopsiya-10-01",
	"Электрокардиография(ЭКГ)" : "https://telegra.ph/EHlektrokardiografiya-10-01",
	"Компьютерная томография(КТ)" : "https://telegra.ph/Kompyuternaya-tomografiya-KT-10-01",
	"Кровоснабжение мозга" : "https://telegra.ph/Krovosnabzhenie-mozga-10-01",
	"Ангиография" : "https://telegra.ph/Angiografiya-10-01",
	"Ишемическая болезнь сердца(ИБС)" : "https://telegra.ph/Ishemicheskaya-bolezn-serdca-IBS-10-01",
	"Напряжение глаз" : "https://telegra.ph/Napryazhenie-glaz-10-01",
	"Проверка зрения" : "https://telegra.ph/Proverka-zreniya-10-01",
	"Как уменьшить головную боль" : "https://telegra.ph/Kak-umenshit-golovnuyu-bol-10-01",
	"Как сохраняется равновесие" : "https://telegra.ph/Kak-sohranit-ravnovesie-10-01",
	"Психотерапия" : "https://telegra.ph/Psihoterapiya-10-01",
	"Что такое стресс?" : "https://telegra.ph/CHto-takoe-stress-10-01",
	"Сексуальная ориентация у мужчин" : "https://telegra.ph/Seksualnaya-orientaciya-10-01",
	"Сексуальная ориентация у женщин" : "https://telegra.ph/Seksualnaya-orientaciya-10-01-2",
	"Менструальный цикл" : "https://telegra.ph/Menstrualnyj-cikl-10-01",
	"Лечение менструальных состояний" : "https://telegra.ph/Lechenie-menstrualnyh-sostoyanij-10-01",
	"Консультация сексолога" : "https://telegra.ph/Beseda-s-seksologom-10-01-2",
	"Беседа с сексологом" : "https://telegra.ph/Beseda-s-seksologom-10-01",
	"Уход за волосами" : "https://telegra.ph/Uhod-za-volosami-10-01-2",
	"Строение кожи" : "https://telegra.ph/Stroenie-kozhi-10-01",
	"Краснуха и беременность" : "https://telegra.ph/Krasnuha-i-beremennost-10-01",
	"Первая помощь при травмах глаза" : "https://telegra.ph/Pervaya-pomoshch-pri-travmah-glaza-u-vzroslyh-10-01",
 	"Первая помощь при попадании насекомого в ухо" : "https://telegra.ph/Pervaya-pomoshch-pri-popadanii-nasekomogo-v-uho-10-01",
	"Глухота и беременность" : "https://telegra.ph/Gluhota-i-beremennost-10-01",
	"Как облегчить боль в горле" : "https://telegra.ph/Kak-oblegchit-bol-v-gorle-10-01",
	"Эпидемический паротит и бесплодие" : "https://telegra.ph/EHpidemicheskij-parotit-i-besplodie-10-01",
	"Последствия курения" : "https://telegra.ph/Posledstviya-kureniya-10-01",
	"Лечение ларингита" : "https://telegra.ph/Lechenie-laringita-10-01",
	"Бронхоскопия" : "https://telegra.ph/Bronhoskopiya-10-01",
	"Приступы паники" : "https://telegra.ph/Pristupy-paniki-10-01",
	"Уход за зубами" : "https://telegra.ph/Uhod-za-zubami-10-01",
	"Уход за зубными протезами" : "https://telegra.ph/Uhod-za-zubnymi-protezami-10-01",
	"Лечение рвоты" : "https://telegra.ph/Lechenie-rvoty-10-01",
	"Рекомендации при гастроэнтерите" : "https://telegra.ph/Rekomendacii-pri-gastroehnterite-10-01",
	"Удаление желчного пузыря" : "https://telegra.ph/Udalenie-zhelchnogo-puzyrya-10-01",
	"Выкидыш" : "https://telegra.ph/Vykidysh-10-01",
	"Спастический колит" : "https://telegra.ph/Spasticheskij-kolit-10-01",
	"Преимущества диеты с большим содержанием клетчатки" : "https://telegra.ph/Polza-kletchatki-10-01",
	"Увеличение предстательной железы" : "https://telegra.ph/Uvelichenie-predstatelnoj-zhelezy-10-01",
	"Понос путешественника" : "https://telegra.ph/Ponos-puteshestvennika-10-01",
	"Лечение геморроя" : "https://telegra.ph/Lechenie-gemorroya-10-01",
	"Рекомендации при болях в спине" : "https://telegra.ph/Rekomendacii-pri-bolyah-v-spine-10-01",
	"Варикозное расширение вен" : "https://telegra.ph/Varikoznoe-rasshirenie-ven-10-01",
	"Причины облысения у мужчин" : "https://telegra.ph/Prichiny-oblyseniya-u-muzhchin-10-01",
	"Гигиена половых органов у мужчин" : "https://telegra.ph/Gigiena-polovyh-organov-muzhchin-10-01",
	"Гигиена половых органов у женщин" : "https://telegra.ph/Gigiena-polovyh-organov-zhenshchin-10-01",
	"Венерические болезни" : "https://telegra.ph/Venericheskie-bolezni-10-01",
	"Метод сдавливания" : "https://telegra.ph/Metod-sdavlivaniya-10-01",
	"Снятие сексуальной тревоги" : "https://telegra.ph/Snyatie-seksualnoj-trevogi-10-01",
	"Рекомендации при задержке семяизвержения" : "https://telegra.ph/Rekomendacii-pri-zaderzhke-semyaizverzheniya-10-01",
	"Половая жизнь и возраст" : "https://telegra.ph/Polovaya-zhizn-i-vozrast-muzhchiny-10-01",
	"Многочисленные половые партнеры" : "https://telegra.ph/Mnogochislennye-polovye-partnery-10-01",
	"Анализ спермы" : "https://telegra.ph/Analiz-spermy-10-01",
	"Вазэктомия" : "https://telegra.ph/Vazehktomiya-10-01",
	"Увеличение возможности зачатия" : "https://telegra.ph/Uvelichenie-vozmozhnosti-zachatiya-10-01",
	"Способы предохранения для женщин" : "https://telegra.ph/Sposoby-predohraneniya-10-01",
	"Прерывание беременности" : "https://telegra.ph/Preryvanie-beremennosti-10-01",
	"Образование спермы" : "https://telegra.ph/Obrazovanie-spermy-10-01",
	"Самообследование молочных желез" : "https://telegra.ph/Samoobsledovanie-molochnyh-zhelez-10-01",
	"Рак молочной железы" : "https://telegra.ph/Rak-molochnoj-zhelezy-10-01",
	"Выскабливание матки" : "https://telegra.ph/Vyskablivanie-matki-10-01",
	"Гистерэктомия" : "https://telegra.ph/Gisterehktomiya-10-01",
	"Лапароскопия" : "https://telegra.ph/Laparoskopiya-10-01",
	"Исследование шейки матки" : "https://telegra.ph/Issledovanie-shejki-matki-10-01",
	"Исследование мочевого пузыря" : "https://telegra.ph/Issledovanie-mochevogo-puzyrya-10-01",
	"Упражнения для мышц таза" : "https://telegra.ph/Uprazhneniya-dlya-myshc-taza-10-01",
	"Рекомендации при инфекционных заболеваниях мочевого пузыря и уретры" : "https://telegra.ph/Rekomendacii-pri-infekcionnyh-zabolevaniyah-mochevogo-puzyrya-i-uretry-10-01",
	"Цистоскопия" : "https://telegra.ph/Cistoskopiya-10-01",
	"Стерилизация" : "https://telegra.ph/Sterilizaciya-10-01",
	"Как справиться с тошнотой и рвотой" : "https://telegra.ph/Kak-spravitsya-s-toshnotoj-i-rvoto-10-01",
	"Рекомендации при изжоге" : "https://telegra.ph/Rekomendacii-pri-izzhoge-10-01",
	"Стимуляция родов" : "https://telegra.ph/Stimulyaciya-rodov-10-01",
	"Холецистография" : "https://telegra.ph/Holecistografiya-10-10",

}

symptom_dict = {}

for i in range(len(symptom_list)):
	symptom_dict[symptom_list[i]] = i + 1


def mes_from_nav_dict(text, uid):
	print('mes_from_nav_dict')
	mes_path = []
	find_section(nav_dict, text, [], mes_path)
	user_states[uid]['nav_path'] = mes_path
	print('mespath', mes_path)
	return mes_path


def find_section(context, section, path, mes_path):
	for key in context.keys():
		if key == section:
			print('path', path)
			for p in path:
				mes_path.append(p)
		elif not(isinstance(context[key], str)):
			path.append(key)
			find_section(context[key], section, path, mes_path)
			path.pop()
	



@bot.message_handler(func=lambda message: True)
def find_symptoms(message, called_from=''):
	try:
		
		print('from find symptoms', user_states)
		answers = '' 
		schema_is_open = 0
		continue_execution = 1
		u_id = message.chat.id
		if u_id not in users:
			save_user_info(message)
		if u_id in user_states:
			if user_states[message.chat.id]['next_func'] == 'nav':
				navigate(message)
				continue_execution = 0
			elif user_states[message.chat.id]['next_func'] == 'on_click':
				on_click(message)
				continue_execution = 0
			u = user_states[u_id]
			(from_inline, answers,nav_path, current_article, schema_is_open,data_from_db) = (u['from_inline'], u['answers'],u['nav_path'], u['current_article'], u['schema_is_open'], u['data_from_db'])
		else:
			res = import_user_state(u_id)
			if res is None:
				create_state(u_id)
			elif called_from == '':
				if res['current_article'] == '0':
					navigate(message)
				else:
					on_click(message)
				continue_execution = 0
		if continue_execution == 0:
			pass
		elif (str(message.text).strip()[0]).isnumeric():
			num = ""
			str_text = str(message.text).strip()
			i = 0
			while i < len(str_text) and str_text[i].isnumeric() :
				num += str_text[i]
				i += 1
			num = int(num)
			if num < 148 and num > 0:
				open_article(num, message)
			else:
				bot.reply_to(message, f'Схемы c таким номером не существует 😔 (Есть от 1 до 147). Попробуйте найти нужную схему с помощью меню')
				user_states[u_id]['nav_path'] = []
				message.text = 'Начать диагностику ➡️'
				navigate(message)
		elif message.text == '/start':
			start(message)
		elif (message.text).lower() in symptom_list:
			current_article = symptom_list.index((message.text).lower()) + 1
			open_article(current_article, message)
		elif mes_from_nav_dict(message.text, u_id):
			print("abra: ",user_states[u_id]['nav_path'], message.text)
			user_states[u_id]['current_article'] = '0'
			user_states[u_id]['schema_is_open'] = 0
			user_states[u_id]['answers'] = ''
			navigate(message)
		elif message.text  in ("Назад","🚪 В меню"):			# еще current_article == 0
			message.text = "🚪 В меню"
			on_click(message)
		else:
			mtext = str(message.text)
			if len(mtext) > 0:
				if len(mtext) > 30:
					mtext = mtext[:30]
				user_states[u_id]['last_query'] = mtext
			user_symps = ((message.text).lower())
			lsymps = len(user_symps)
			res = []
			for key in symptom_tagdict:
				flag = 0
				for tag in symptom_tagdict[key]:
					sintag = user_symps in tag
					tagins = tag in user_symps
					eq = sintag * tagins
					ltag = len(tag)
					if lsymps <= 5:
						if tag == user_symps :
							flag = 1
					elif sintag or tagins:
						print(tag,user_symps)
						flag = 1
				if flag:
					res.append(symptom_list[int(key)-1])
			if len(res) == 0:
				user_states[u_id]['nav_path'] = ['Начать диагностику ➡️']
				user_states[u_id]['current_article'] = '0'
				user_states[u_id]['answers'] = ''
				user_states[u_id]['next_func'] = 'nav'
				markup = types.ReplyKeyboardMarkup()
				context = nav_dict["Начать диагностику ➡️"]
				for key in context:
					btn = types.KeyboardButton(key)
					markup.row(btn)
				backbtn = types.KeyboardButton('Назад')
				markup.row(backbtn)
				bot.reply_to(message, f'Поиск результатов не дал 😔\nПопробуйте найти свою проблему с помощью меню или наберите номер конкретной схемы',reply_markup=markup)
			else:
				markup = types.InlineKeyboardMarkup()
				for r in res:
					markup.add(types.InlineKeyboardButton(r, callback_data=symptom_dict[r]))
				bot.reply_to(message, "Вот, что я нашел 🥳 ", reply_markup=markup)
	except Exception as err:
		handle_exception(message, traceback.format_exc())


@bot.callback_query_handler(func=lambda callback: True)
def open_article(callback, mes=0):
	try:
		print('from open_article',user_states)
		answers = ''
		schema_is_open = 0
		from_inline = 0
		nav_path = []
		continue_execution = 1
		u_id = 0
		if mes:
			u_id = mes.chat.id
		else:
			u_id = callback.message.chat.id
		if u_id in user_states:
			u = user_states[u_id]
			(current_article, answers, schema_is_open, from_inline, nav_path) = (u['current_article'],u['answers'],u['schema_is_open'],u['from_inline'],u['nav_path'])
		else:
			create_state(u_id)
			(current_article, answers, schema_is_open, from_inline, nav_path) = ('0','',0,0,[])

		if str(callback).strip()[0].isnumeric():
			num = ""
			str_text = str(callback).strip()
			i = 0
			while i < len(str_text) and str_text[i].isnumeric():
				num += str_text[i]
				i += 1
			num = int(num)
			if num < 148 and num > 0:
				current_article = num
				answers = ""
			else:
				bot.reply_to(mes, f'Схемы c таким номером не существует 😔 (Есть от 1 до 147). Попробуйте найти нужную схему с помощью меню')
				user_states[u_id]['nav_path'] = []
				user_states[u_id]['current_article'] = '0'

				mes.text = 'Начать диагностику ➡️'
				continue_execution = 0
				navigate(mes)
		else:
			current_article = str(callback.data)					
			answers = ""

		if continue_execution:
			nav_path = []
			f_path = './images/' + str(current_article) + '/' +'info0.png'
			file = open(f_path, 'rb')
			schema_is_open = 0
			markup = types.ReplyKeyboardMarkup()
			openbtn = types.KeyboardButton('Пройти схему ➡️')
			markup.row(openbtn)
			if str(current_article) in links_dict and "info0" in links_dict[str(current_article)]:
				for link in links_dict[str(current_article)]["info0"]:
					linkbtn = types.KeyboardButton(link)
					markup.row(linkbtn)
			backbtn = types.KeyboardButton('Назад')
			markup.row(backbtn)
			create_state(u_id)
			user_states[u_id]['current_article'] = str(current_article)
			caption = ''
			c_art = str(current_article)
			if c_art in warnings:
				caption = f"‼️<a href=\"{warnings[c_art]}\">Важно знать</a>‼️"
			if(mes == 0):
				bot.send_photo(u_id, file, caption, reply_markup=markup)
			else:
				bot.send_photo(mes.chat.id, file, caption, reply_markup=markup)
			user_states[u_id]['next_func'] = 'on_click'
			file.close()
	except Exception as err:
		if(mes):
			handle_exception(mes, traceback.format_exc())
		else:
			handle_exception(callback.message, traceback.format_exc())




bot.polling(none_stop=True, interval=0)












#@bot.message_handler(commands=['site','website'])

#def site(message):
#	webbrowser.open('https://m.vk.com')

'''
@bot.message_handler(commands=['main','hello','start'])
#создаем декоратор для методаmessage_handler
# теперт при каждом юзании команды старт будет
# срабатывать функция ниже

def main(message):
	bot.send_message(message.chat.id,f'Привет, {message.from_user.first_name} {message.from_user.last_name}')



@bot.message_handler(commands=['help'])

def help_info(message):
	bot.send_message(message.chat.id,'<b>справочная</b> <u><em>информация</em></u>',parse_mode='html')

@bot.message_handler(commands=['weather'])

def weather_info(message):
	bot.send_message(message.chat.id,"Введите ваш город на латинице(например: tver)")
#	bot.send_message(message.chat.id,f'Температура в {CITY} сейчас: {temperature} градусов. Описание погоды: {report[0]["description"]}')

@bot.message_handler(func=lambda message: True)
def echo_message(message):
	CITY = (message.text).capitalize()
	BASE_URL = "https://api.openweathermap.org/data/2.5/weather?"
	API_KEY = "2af2ba9e8b04993276527aab3b50088b"

	URL = BASE_URL+"q="+CITY+"&appid="+API_KEY
	report =""
	temperature = 0
	response = requests.get(URL)

	if response.status_code == 200:
		data = response.json()
		main = data['main']
		temperature = int(main['temp']) - 273
		grads = "градусов"
		if temperature%10 ==1 and temperature != 11:
			grads = "градус"
		elif temperature%10 in (2,3,4):
			grads = "градуса"
		humidity = main['humidity']
		pressure = main['pressure']
		wind_speed = int(data['wind']['speed'])
		wind_em = "🌬"
		if wind_speed >3:
			wind_em = "🌬💨"
		elif wind_speed >6:
			wind_em ="🌬💨💨" 
		report = data['weather']
		desc = report[0]["description"]
		if desc =="fog":
			desc ="туман 🌫🌫"
		elif desc == "broken clouds":
			desc ="малооблачно ⛅️"
		elif desc == "few clouds":
			desc ="небольшая облачность ⛅️"
		elif desc == "overcast clouds":
			desc = "пасмурно 🌫"
		elif desc == "clear sky":
			desc = "ясно ☀️"
		elif desc == "scattered clouds":
			desc = "редкие облака 🌤"
		bot.send_message(message.chat.id,f'Температура в {CITY} сейчас: {temperature} {grads}. \nВетер: {wind_speed}м/с {wind_em}\nОписание погоды: {desc}')
	else:
		bot.reply_to(message, f'Город {CITY} не найден. Попробуйте еще раз')




@bot.message_handler()
def info(message):
	if message.text.lower() =='привет':
		bot.send_message(message.chat.id,f'привет, {message.from_user.first_name} {message.from_user.last_name}')
	elif message.text.lower()=='id':
		bot.reply_to(message,f'ID:{message.from_user.id}')
	elif message.text.lower() in('/weather','погода'):
		bot.reply_to(message,f'Температура в {CITY} сейчас: {temperature} градусов. Описание погоды: {report[0]["description"]}')


#keep_alive()
'''

