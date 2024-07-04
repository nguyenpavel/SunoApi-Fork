# -*- coding:utf-8 -*-

import streamlit as st
from streamlit_option_menu import option_menu
import streamlit.components.v1 as components
import time, json, os, requests
from datetime import timezone
import dateutil.parser
from datetime import datetime
from pathlib import Path

import schemas
from cookie import get_suno_auth, new_suno_auth, start_keep_alive, get_random_token, get_page_token
from utils import generate_lyrics, generate_music, get_feed, get_page_feed, get_lyrics, check_url_available, local_time, get_random_style, get_random_lyrics, put_upload_file, get_new_tags, suno_upload_audio

root_dir = os.path.dirname(os.path.realpath(__file__))
# print(root_dir)
import sys
sys.path.append(root_dir)
import site
site.addsitedir(root_dir)
from streamlit_image_select import image_select

from dotenv import load_dotenv
load_dotenv()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
S3_WEB_SITE_URL = os.getenv("S3_WEB_SITE_URL")
S3_ACCESSKEY_ID = os.getenv("S3_ACCESSKEY_ID")
S3_SECRETKEY_ID = os.getenv("S3_SECRETKEY_ID")

from sqlite import SqliteTool

suno_sqlite = SqliteTool()

st.set_page_config(page_title="SunoAPI AI Music Generator",
                   page_icon="🎵",
                   layout="wide",
                   initial_sidebar_state="collapsed",
                   menu_items={
                       'Report a bug': "https://github.com/SunoApi/SunoApi/issues",
                       'About': "SunoAPI AI Music Generator is a free AI music generation software, calling the existing API interface to achieve AI music generation. If you have any questions, please visit our website url address: https://sunoapi.net\n\nDisclaimer: Users voluntarily input their account information that has not been recharged to generate music. Each account can generate five songs for free every day, and we will not use them for other purposes. Please rest assured to use them! If there are 10000 users, the system can generate 50000 songs for free every day. Please try to save usage, as each account can only generate five songs for free every day. If everyone generates more than five songs per day, it is still not enough. The ultimate goal is to keep them available for free generation at any time when needed.\n\n"
                   })

hide_streamlit_style = """
<style>#root > div:nth-child(1) > div > div > div > div > section > div {padding-top: 2rem;}</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

i18n_dir = os.path.join(root_dir, "i18n")
# print(i18n_dir)

def load_locales():
    locales = {}
    for root, dirs, files in os.walk(i18n_dir):
        for file in files:
            if file.endswith(".json"):
                lang = file.split(".")[0]
                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                    locales[lang] = json.loads(f.read())
    return locales

locales = load_locales()
display_languages = []

if 'Language' not in st.session_state:
    st.session_state.selected_index = 7
    st.session_state.Language = "EN"  # Default to Czech

for i, code in enumerate(locales.keys()):
    display_languages.append(f"{code} - {locales[code].get('Language')}")
    if code == st.session_state.Language:
        st.session_state.selected_index = i
        st.session_state.Language = code

def change_language():
    for item in display_languages:
        if item == st.session_state.selectbox_value:
            st.session_state.selected_index = display_languages.index(item)
            st.session_state.Language = item.split(" - ")[0]

col1, col2, col3 = st.columns(3)

col2.selectbox(label="Language", options=display_languages, label_visibility='collapsed', index=st.session_state.selected_index, key="selectbox_value", on_change=change_language)

def i18n(key):
    loc = locales.get(st.session_state.Language, {})
    return loc.get("Translation", {}).get(key, key)

st.session_state["page"] = 1
st.session_state["click_image"] = False

with st.sidebar:
    selected = option_menu(None, [i18n("Music Song Create"), i18n("Music Share Square"), i18n("Music Project Readme"), i18n("Visit Official WebSite")], icons=['music-note', 'music-note-beamed', 'music-note-list'], menu_icon="cast", default_index=0)
    
    if selected == i18n("Music Share Square"):
        st.switch_page("pages/square.py")
    elif selected == i18n("Music Project Readme"):
        st.switch_page("pages/readme.py")
    elif selected == i18n("Visit Official WebSite"):
        st.page_link("https://suno.com", label=i18n("Visit Official WebSite1"), icon="🌐")
        st.page_link("https://sunoapi.net", label=i18n("Visit Official WebSite2"), icon="🌐")

st.sidebar.image('https://sunoapi.net/images/wechat.jpg', caption=i18n("Join WeChat Group"))
st.sidebar.markdown(f'<div data-testid="stImageCaption" class="st-emotion-cache-1b0udgb e115fcil0" style="max-width: 100%;"> {i18n("Friendly Link")}</div>', unsafe_allow_html=True)
result = suno_sqlite.query_many("select link, label, status from link where status=0 order by id")
if result is not None and len(result) > 0:
    for row in result:
        st.sidebar.page_link(row[0], label=row[1], icon="🌐")

col2.title(i18n("Page Title"))

col2.markdown(i18n("Page Header"))

container = col2.container(border=True)

def change_tags():
    st.session_state['tags_input'] = st.session_state['change_tags']

def change_prompt():
    st.session_state['prompt_input'] = st.session_state['change_prompt']

def change_desc_prompt():
    st.session_state.DescPrompt = st.session_state['change_desc_prompt']

placeholder = col2.empty()
if 'disabled_state' not in st.session_state:
        st.session_state['disabled_state'] = False
elif st.session_state['disabled_state']:
    placeholder.error(i18n("Fetch Status Progress"))

if 'prompt_input' not in st.session_state:
    st.session_state['prompt_input'] = ""
if 'DescPrompt' not in st.session_state:
    st.session_state.DescPrompt = ""

if 'continue_at' not in st.session_state:
    st.session_state['continue_at'] = None
if 'continue_clip_id' not in st.session_state:
    st.session_state['continue_clip_id'] = None

if 'model_name' not in st.session_state:
    st.session_state['model_name'] = "chirp-v3-5"

# @st.cache_data
def fetch_feed(aids: list, token: str):
    if len(aids) == 1 and len(aids[0].strip()) == 36:
        resp = get_feed(aids[0].strip(), token)
        print(resp)
        print("\n")
        status = resp["detail"] if "detail" in resp else resp[0]["status"]
        if status != "Unauthorized" and status != "Not found." and status != "error" and "refused" not in status:
            result = suno_sqlite.query_one("select aid from music where aid =?", (aids[0].strip(),))
            print(result)
            print("\n")
            if result:
                result = suno_sqlite.operate_one("update music set data=?, updated=(datetime('now', 'localtime')), sid=?, name=?, image=?, title=?, tags=?, prompt=?, duration=?, status=? where aid =?", (str(resp[0]), resp[0]["user_id"], resp[0]["display_name"], resp[0]["image_url"], resp[0]["title"], resp[0]["metadata"]["tags"], resp[0]["metadata"]["gpt_description_prompt"], resp[0]["metadata"]["duration"], resp[0]["status"], aids[0].strip()))
            else:
                result = suno_sqlite.operate_one("insert into music (aid, data, sid, name, image, title, tags, prompt, duration, status, private) values(?,?,?,?,?,?,?,?,?,?,?)", (str(resp[0]["id"]), str(resp[0]), resp[0]["user_id"], resp[0]["display_name"], resp[0]["image_url"], resp[0]["title"], resp[0]["metadata"]["tags"], resp[0]["metadata"]["gpt_description_prompt"], resp[0]["metadata"]["duration"], resp[0]["status"], st.session_state.Private))
            print(result)
            print("\n")
            if status == "complete":
                st.balloons()
                col1.audio(resp[0]["audio_url"] + "?play=true")
                col1.video(resp[0]["video_url"] + "?play=true")
                placeholder.empty()
                col2.success(i18n("FetchFeed Success") + resp[0]["id"])
            else:
                placeholder.error(i18n("FetchFeed Error") + (status if "metadata" not in resp else resp[0]['metadata']["error_message"]))
        else:
            placeholder.error(i18n("FetchFeed Error") + (status if "metadata" not in resp else resp[0]['metadata']["error_message"]))
    elif len(aids) == 2 and len(aids[0].strip()) == 36 and len(aids[1].strip()) == 36:
        resp = get_feed(aids[0].strip(), token)
        print(resp)
        print("\n")
        status = resp["detail"] if "detail" in resp else resp[0]["status"]
        if status != "Unauthorized" and status != "Not found." and status != "error" and "refused" not in status:
            result = suno_sqlite.query_one("select aid from music where aid =?", (aids[0].strip(),))
            print(result)
            print("\n")
            if result:
                result = suno_sqlite.operate_one("update music set data=?, updated=(datetime('now', 'localtime')), sid=?, name=?, image=?, title=?, tags=?, prompt=?, duration=?, status=? where aid =?", (str(resp[0]), resp[0]["user_id"], resp[0]["display_name"], resp[0]["image_url"], resp[0]["title"], resp[0]["metadata"]["tags"], resp[0]["metadata"]["gpt_description_prompt"], resp[0]["metadata"]["duration"], resp[0]["status"], aids[0].strip()))
            else:
                result = suno_sqlite.operate_one("insert into music (aid, data, sid, name, image, title, tags, prompt, duration, status, private) values(?,?,?,?,?,?,?,?,?,?,?)", (str(resp[0]["id"]), str(resp[0]), resp[0]["user_id"], resp[0]["display_name"], resp[0]["image_url"], resp[0]["title"], resp[0]["metadata"]["tags"], resp[0]["metadata"]["gpt_description_prompt"], resp[0]["metadata"]["duration"], resp[0]["status"], st.session_state.Private))
            print(result)
            print("\n")
            if status == "complete":
                col1.audio(resp[0]["audio_url"] + "?play=true")
                col1.video(resp[0]["video_url"] + "?play=true")
                col2.success(i18n("FetchFeed Success") + resp[0]["id"])
            else:
                placeholder.error(i18n("FetchFeed Error") + (status if "metadata" not in resp else resp[0]['metadata']["error_message"]))
        else:
            placeholder.error(i18n("FetchFeed Error") + (status if "metadata" not in resp else resp[0]['metadata']["error_message"]))

        resp = get_feed(aids[1].strip(), token)
        print(resp)
        print("\n")
        status = resp["detail"] if "detail" in resp else resp[0]["status"]
        if status != "Unauthorized" and status != "Not found." and status != "error" and "refused" not in status:
            result = suno_sqlite.query_one("select aid from music where aid =?", (aids[1].strip(),))
            print(result)
            print("\n")
            if result:
                result = suno_sqlite.operate_one("update music set data=?, updated=(datetime('now', 'localtime')), sid=?, name=?, image=?, title=?, tags=?, prompt=?, duration=?, status=? where aid =?", (str(resp[0]), resp[0]["user_id"], resp[0]["display_name"], resp[0]["image_url"], resp[0]["title"], resp[0]["metadata"]["tags"], resp[0]["metadata"]["gpt_description_prompt"], resp[0]["metadata"]["duration"], resp[0]["status"], aids[1].strip()))
            else:
                result = suno_sqlite.operate_one("insert into music (aid, data, sid, name, image, title, tags, prompt, duration, status, private) values(?,?,?,?,?,?,?,?,?,?,?)", (str(resp[0]["id"]), str(resp[0]), resp[0]["user_id"], resp[0]["display_name"], resp[0]["image_url"], resp[0]["title"], resp[0]["metadata"]["tags"], resp[0]["metadata"]["gpt_description_prompt"], resp[0]["metadata"]["duration"], resp[0]["status"], st.session_state.Private))
            print(result)
            print("\n")
            if status == "complete":
                st.balloons()
                col3.audio(resp[0]["audio_url"] + "?play=true")
                col3.video(resp[0]["video_url"] + "?play=true")
                col2.success(i18n("FetchFeed Success") + resp[0]["id"])
            else:
                placeholder.error(i18n("FetchFeed Error") + (status if "metadata" not in resp else resp[0]['metadata']["error_message"]))
        else:
            placeholder.error(i18n("FetchFeed Error") + (status if "metadata" not in resp else resp[0]['metadata']["error_message"]))
    else:
        resp = get_page_feed(aids, token)
        print(resp)
        print("\n")
        status = resp["detail"] if "detail" in resp else resp[0]["status"]
        if status != "Unauthorized" and status != "Not found." and status != "error" and "refused" not in status:
            if len(resp) > 1:
                for row in resp:
                    print(row)
                    print("\n")
                    result = suno_sqlite.query_one("select aid from music where aid =?", (row["id"],))
                    print(result)
                    print("\n")
                    if result:
                        result = suno_sqlite.operate_one("update music set data=?, updated=(datetime('now', 'localtime')), sid=?, name=?, image=?, title=?, tags=?, prompt=?, duration=?, status=? where aid =?", (str(row), row["user_id"], row["display_name"], row["image_url"], row["title"], row["metadata"]["tags"], row["metadata"]["gpt_description_prompt"], row["metadata"]["duration"], row["status"], row["id"]))
                        print(local_time() + f" ***get_page_feed_update page -> {aids} ***\n")
                    else:
                        result = suno_sqlite.operate_one("insert into music (aid, data, sid, name, image, title, tags, prompt, duration, created, updated, status, private) values(?,?,?,?,?,?,?,?,?,?,?,?,?)", (str(row["id"]), str(row), row["user_id"], row["display_name"], row["image_url"], row["title"], row["metadata"]["tags"], row["metadata"]["gpt_description_prompt"], row["metadata"]["duration"], localdatetime(row['created_at']), localdatetime(row['created_at']), row["status"], st.session_state.Private))
                        print(local_time() + f" ***get_page_feed_insert page -> {aids} ***\n")
                    print(result)
                    print("\n")
                    status = resp["detail"] if "detail" in resp else row["status"]
                    if status == "complete":
                        placeholder.success(i18n("FetchFeed Success") + row["id"])
                    else:
                        placeholder.error(i18n("FetchFeed Error") + (status if "metadata" not in resp else row['metadata']["error_message"]))
            else:
                placeholder.error(i18n("FetchFeed Error") + resp["detail"][0]["msg"])
        else:
            placeholder.error(i18n("FetchFeed Error") + status)

with container.container():
    cols = container.columns(3)
    
    #Pavel
    #st.session_state.Custom = True
    #if (st.session_state['continue_at'] and st.session_state['continue_clip_id']) or st.session_state['prompt_input']:
    #    Custom = cols[0].toggle(i18n("Custom"), True)
    #else:
    #    Custom = cols[0].toggle(i18n("Custom"))
        
    #st.session_state.TuGeYue = False
    #TuGeYue = cols[1].toggle(i18n("Images TuGeYue Music"))
    #st.session_state.YueShengQu = False
    #YueShengQu = cols[2].toggle(i18n("Upload Audio Music"))

    # if TuGeYue and st.session_state.DescPrompt == "" and st.session_state['prompt_input'] == "":
    #     st.session_state.TuGeYue = True
    #     upload_folder = Path("images/upload")
    #     upload_folder.mkdir(exist_ok=True)
    #     file_size_limit = 1024 * 1024 * 3  # 3MB
    #     uploaded_file = container.file_uploader(i18n("Images TuGeYue Upload"), type=['bmp', 'webp', 'png', 'jpg', 'jpeg'], help=i18n("Images TuGeYue Help"), accept_multiple_files=False)

    #     if uploaded_file is not None and not st.session_state['disabled_state']:
    #         if uploaded_file.size > file_size_limit:
    #             placeholder.error(i18n("Upload Images Error") + f"{file_size_limit / (1024 * 1024)}MB")
    #         else:
    #             file_ext = uploaded_file.type.split("/")[1]
    #             filename = f"{time.time()}.{file_ext}"
    #             my_bar = container.progress(0)
    #             bytes_data = uploaded_file.read()
    #             with open(upload_folder / filename, "wb") as f:
    #                 f.write(bytes_data)
    #             my_bar.progress(100)
    #             image_url = ""
    #             if "s3.bitiful.net" in S3_WEB_SITE_URL:
    #                 image_url = put_upload_file(S3_WEB_SITE_URL, filename, S3_ACCESSKEY_ID, S3_SECRETKEY_ID, bytes_data)
    #             elif S3_WEB_SITE_URL != "https://res.sunoapi.net":
    #                 image_url = f"{S3_WEB_SITE_URL}/images/upload/{filename}"
    #             elif S3_WEB_SITE_URL == "https://res.sunoapi.net":
    #                 image_url = f"https://sunoapi.net/images/upload/{filename}"
    #             else:
    #                 image_url = "http://localhost:8501/images/upload/{filename}"
    #             if "detail" in image_url:
    #                 placeholder.error(i18n("Analytics Images Error") + image_url["detail"])
    #             else:
    #                 placeholder.success(i18n("Upload Images Success"))
    #                 my_bar.empty()
    #                 try:
    #                     headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    #                     requests.packages.urllib3.disable_warnings()
    #                     resp = requests.post(
    #                         url=f"{OPENAI_BASE_URL}/v1/chat/completions",
    #                         headers=headers,
    #                         verify=False,
    #                         json={
    #                             "messages": [
    #                                 {
    #                                     "role": "user",
    #                                     "content": [
    #                                         {
    #                                             "type": "text",
    #                                             "text": i18n("Upload Images Analytics")
    #                                         },
    #                                         {
    #                                             "type": "image_url",
    #                                             "image_url": {
    #                                                 "url": image_url
    #                                             }
    #                                         }
    #                                     ]
    #                                 }
    #                             ],
    #                             "max_tokens": 1000,
    #                             "temperature": 1,
    #                             "top_p": 1,
    #                             "n": 1,
    #                             "stream": False,
    #                             "presence_penalty": 0,
    #                             "frequency_penalty": 0,
    #                             "model": "gpt-4o"
    #                         }
    #                     )
    #                     if resp.status_code != 200:
    #                         placeholder.error(i18n("Analytics Images Error") + f"{resp.text}")
    #                     else:
    #                         print(local_time() + f" ***gpt-4o image_url -> {image_url} content -> {resp.text} ***\n")
    #                         content = resp.json()["choices"][0]["message"]["content"].strip()
    #                         if Custom:
    #                             st.session_state['prompt_input'] = content
    #                         else:
    #                             st.session_state.DescPrompt = content
    #                         placeholder.success(i18n("Analytics Images Success"))
    #                 except Exception as e:
    #                     placeholder.error(i18n("Analytics Images Error") + f"{str(e)}")

    # if YueShengQu and st.session_state.DescPrompt == "" and st.session_state['prompt_input'] == "":
    #     st.session_state.YueShengQu = True
    #     upload_folder = Path("audios/upload")
    #     upload_folder.mkdir(exist_ok=True)
    #     file_size_limit = 1024 * 1024 * 3  # 3MB
    #     uploaded_audio = container.file_uploader(i18n("Upload Audio Files"), type=['mp3', 'wav'], help=i18n("Upload Audio Help"), accept_multiple_files=False)

    #     if uploaded_audio is not None and not st.session_state['disabled_state']:
    #         if uploaded_audio.size > file_size_limit:
    #             placeholder.error(i18n("Upload Audio Error") + f"{file_size_limit / (1024 * 1024)}MB")
    #         else:
    #             file_ext = uploaded_audio.type.split("/")[1]
    #             filename = f"{time.time()}.mp3"
    #             my_bar = container.progress(0)
    #             bytes_data = uploaded_audio.read()
    #             with open(upload_folder / filename, "wb") as f:
    #                 f.write(bytes_data)
    #             my_bar.progress(10)
    #             token = get_random_token()
    #             audio_id = suno_upload_audio(uploaded_audio.name, bytes_data, token, my_bar)
    #             if "detail" in audio_id:
    #                 placeholder.error(i18n("Analytics Audio Error") + audio_id["detail"])
    #                 my_bar.empty()
    #             else:
    #                 fetch_feed(audio_id.split(","), token)
    #                 my_bar.progress(100)
    #                 placeholder.success(i18n("Upload Audio Success"))
    #                 my_bar.empty()

    if Custom:
        st.session_state.Custom = True

        if 'title_input' not in st.session_state:
            st.session_state['title_input'] = ""

        Title = container.text_input(label=i18n("Title"), value=st.session_state['title_input'], placeholder=i18n("Title Placeholder"), max_chars=100, help=i18n("Title Desc"))
        st.session_state.Title = Title

        if 'tags_input' not in st.session_state:
            st.session_state['tags_input'] = ""

        if (st.session_state['continue_at'] and st.session_state['continue_clip_id']) or st.session_state['tags_input']:
            Tags = container.text_input(label=i18n("Tags"), value=st.session_state['tags_input'], placeholder=i18n("Tags Placeholder"), max_chars=120, help=i18n("Tags Desc"), key="change_tags", on_change=change_tags)
            st.session_state.Tags = st.session_state['tags_input']
        else:
            options = container.multiselect(
                i18n("Tags"), ["1960s", "Adhan", "Afro-Cuban", "Afrobeat", "Aggressive", "Ambient", "Art", "Arabian", "BackGround", "Bangra", "Banger", "Barbershop", "Bedroom", "Bebop", "Big Band", "Black Metal", "Blues Rock", "Bluegrass", "Bossa Nova", "Broadway", "Cabaret", "Calypso", "Call to Prayer", "Carnival", "Children", "Children's", "Chinese pop", "Chillwave", "Classic", "Classic Rock", "Country", "Dance", "Dance Pop", "Danceable", "Dancehall", "Dark", "Death Metal", "Deathcore", "Disco", "Disco Funk", "Doo Wop", "Downtempo", "Dramatic", "Drum'n'bass", "Dub", "Dubstep", "EDM", "Electro", "Electric", "Elevator", "Emo", "Ethereal", "Festive Heavy Metal", "Forró", "Folk", "Funk", "Glam", "Glam Rock", "Glitter", "Gospel", "Grooveout", "Groovy", "Hard", "Haunted", "Heavy Metal", "High-NRG", "HipHop", "Hollow", "House", "I Want Song", "IDM", "Indie", "Industrial Rock", "Intimate", "Jazz", "Jazz/Soul", "Jewish Music", "Jingle", "Jpop", "Klezmer", "Kpop", "Latin", "Latin Jazz", "Lounge", "Lullaby", "Lyrical", "Majestic", "Magical", "March", "Metal", "Metalcore", "Middle East", "Minimal", "Misterious", "Musicbox", "Muzak", "Nu", "Nu Metal", "Operatic", "Party", "Phonk", "Polka", "Pop", "Pop Rock", "Popular", "Power", "Power Metal", "Progressive", "Punk", "Random", "Rap", "Reggae", "Reggaeton", "Retro", "RnB", "Rock", "Russian Navy Song", "Salsa", "Sinister", "Sing-along", "Skate Rock", "Skatecore", "Slow", "Soft", "Soul", "Sparse", "Stadium", "Storytelling", "Strut", "Swing", "Synthpop", "Synthwave", "Tango", "Techno", "Theatrical", "Tipsy", "Torch-Lounge", "Traditional", "Trance", "Tribal", "Troubadour", "Vegas", "Weird"],
                [] if st.session_state['tags_input'] == "" else st.session_state['tags_input'].split(","),
                placeholder=i18n("Tags Placeholder"),
                help=i18n("Tags Desc"),
                max_selections=4
            )
            st.session_state.Tags = ','.join(str(opts) for opts in options)

        container.container()
        cols = container.columns(2)
        random_style = cols[0].button(i18n("Random Style"), type="secondary")
        if random_style:
            if (st.session_state['continue_at'] and st.session_state['continue_clip_id']) or st.session_state['prompt_input']:
                tags_input = get_random_style()
                tags_input = get_new_tags(tags_input)
                st.session_state['tags_input'] = tags_input
            else:
                st.session_state['tags_input'] = get_random_style()
            st.rerun()

        random_lyrics = cols[1].button(i18n("Generate Lyrics"), type="secondary")
        if random_lyrics:
            lyrics = get_random_lyrics(Title if Title != "" else st.session_state['prompt_input'], get_random_token())
            status = lyrics["detail"] if "detail" in lyrics else (lyrics["status"] if "status" in lyrics else "success")
            if status != "Unauthorized" and status != "Error" and status != "Expecting value: line 1 column 1 (char 0)":
                st.session_state['title_input'] = lyrics['title'] if lyrics['title'] != "" else Title
                st.session_state['prompt_input'] = lyrics['text'] if lyrics['title'] != "" else (st.session_state['prompt_input'] if st.session_state['prompt_input'] != "" else "")
                st.rerun()
            else:
                container.error(status)

        if st.session_state['continue_at'] and st.session_state['continue_clip_id']:
            Prompt = container.text_area(label=i18n("Prompt"), value=st.session_state['prompt_input'], placeholder=i18n("Extend Placeholder"), height=150, max_chars=3000, help=i18n("Prompt Desc"), key="change_prompt", on_change=change_prompt)
        else:
            Prompt = container.text_area(label=i18n("Prompt"), value=st.session_state['prompt_input'], placeholder=i18n("Prompt Placeholder"), height=150, max_chars=3000, help=i18n("Prompt Desc"), key="change_prompt", on_change=change_prompt)
        st.session_state.Prompt = Prompt
    #Pavel
    #else:
    #    st.session_state.Custom = False

    #    if 'DescPrompt' not in st.session_state:
    #        st.session_state.DescPrompt = ""

    #    DescPrompt = container.text_area(label=i18n("Desc Prompt"), value=st.session_state.DescPrompt, placeholder=i18n("Desc Value"), height=150, max_chars=200, help=i18n("Desc Reamrk"), key="change_desc_prompt", on_change=change_desc_prompt)
    #    st.session_state.DescPrompt = DescPrompt

with container.container():
    cols = container.columns(2)

    st.session_state.Instrumental = False
    instrumental = cols[0].checkbox(i18n("Instrumental"), help=i18n("Instrumental Help"))
    if instrumental:
        st.session_state.Instrumental = True
    else:
        st.session_state.Instrumental = False

    st.session_state.Private = False
    private = cols[1].checkbox(i18n("Private"), help=i18n("Private Help"))
    if private:
        st.session_state.Private = True
    else:
        st.session_state.Private = False

def continue_at_change():
    st.session_state['continue_at'] = st.session_state['continue_at_change']
    print(st.session_state['continue_at'])

if st.session_state['continue_at'] and st.session_state['continue_clip_id']:
    container2 = col2.container(border=True)
    container2.text_input(label=i18n("Extend From"), value=st.session_state['continue_at'], placeholder="", max_chars=6, help=i18n("Extend From Help"), key="continue_at_change", on_change=continue_at_change)
    container2.text_input(label=i18n("Extend From Clip"), value=st.session_state['continue_clip_id'], placeholder="", max_chars=36, help="")

#Pavel
#container2 = col2.container(border=True)
#options1 = container2.multiselect(i18n("Select Model"), ["chirp-v3-0", "chirp-v3-5"], ["chirp-v3-0"] if not st.session_state['model_name'] else st.session_state['model_name'].split(","), placeholder=i18n("Select Model Placeholder"), help=i18n("Select Model Help"), max_selections=1)
#st.session_state['model_name'] = ''.join(str(opts) for opts in options1)

if 'model_name' not in st.session_state:
    st.session_state['model_name'] = "chirp-v3-5"
else:
    st.session_state['model_name'] = "chirp-v3-5"


container1 = col2.container(border=True)

st.session_state.Setting = False
Setting = container1.toggle(i18n("Setting"))

identity = ""
Session = ""
Cookie = ""

if Setting:
    st.session_state.Setting = True

    if "Identity" not in st.session_state:
        pass
    else:
        identity = st.session_state.Identity

    result = suno_sqlite.query_one("select id, identity, [session], cookie from session where identity =?", (identity,))
    print(result)
    print("\n")
    if result:
        identity = result[1]
        Session = result[2]
        Cookie = result[3]

    Identity = container1.text_input(label="Identity:", value=identity, placeholder=i18n("Identity Placeholder"), max_chars=50, help=i18n("Identity Help"))
    st.session_state.Identity = Identity
    Session = container1.text_input(label="Session:", value=Session, placeholder=i18n("Session Placeholder"), max_chars=50, help=i18n("Session Help"))
    st.session_state.Session = Session
    Cookie = container1.text_area(label="Cookie:", value=Cookie, placeholder=i18n("Cookie Placeholder"), height=150, max_chars=1500, help=i18n("Cookie Help"))
    st.session_state.Cookie = Cookie

    st.session_state.SaveInfo = False
    SaveInfo = container1.button(i18n("SaveInfo"))
    if SaveInfo:
        st.session_state.SaveInfo = True
        if Identity == "":
            placeholder.error(i18n("SaveInfo Identity Error"))
        elif Session == "":
            placeholder.error(i18n("SaveInfo Session Error"))
        elif Cookie == "":
            placeholder.error(i18n("SaveInfo Cookie Error"))
        elif len(Cookie) < 500:
            placeholder.error(i18n("SaveInfo Cookie Error"))
        else:
            result = suno_sqlite.query_one("select id, identity, [session], cookie from session where identity =?", (Identity,))
            print(result)
            print("\n")
            if result:
                result = suno_sqlite.operate_one("update session set session=?, cookie=?, token=? where identity =?", (Session, Cookie, Identity, ""))
            else:
                result = suno_sqlite.operate_one("insert into session (identity, session, cookie, token) values(?,?,?,?)", (Identity, Session, Cookie, ""))

            if result:
                st.session_state.Identity = Identity
                new_suno_auth(Identity, Session, Cookie)
                placeholder.empty()
                col2.success(i18n("SaveInfo Success"))
            else:
                placeholder.error(i18n("SaveInfo Error"))
            print(result)
            print("\n")
else:
    st.session_state.SaveInfo = False

st.session_state.token = ""
st.session_state.suno_auth = None

@st.cache_data
def start_page():
    start_keep_alive()
start_page()

def localdatetime(str):
    dateObject = dateutil.parser.isoparse(str)
    localdt = dateObject.replace(tzinfo=timezone.utc).astimezone(tz=None)
    return localdt.strftime('%Y-%m-%d %H:%M:%S')

container2 = col2.container(border=True)

st.session_state.FetchFeed = False
FetchFeed = container2.toggle(i18n("FetchFeed"))

if FetchFeed:
    st.session_state.FetchFeed = True

    FeedID = container2.text_input(label=i18n("FeedID"), value="", placeholder=i18n("FeedID Placeholder"), max_chars=100, help=i18n("FeedID Help"))
    st.session_state.FeedID = FeedID

    st.session_state.FeedBtn = False
    FeedBtn = container2.button(i18n("FeedBtn"))
    if FeedBtn:
        st.session_state.FeedBtn = True
        if FeedID == "":
            placeholder.error(i18n("FetchFeed FeedID Empty"))
        elif "add" in FeedID:
            for item in FeedID.split(" ")[1].split(","):
                result = suno_sqlite.operate_one("update music set private=0 where aid=?", (item,))
                placeholder.success(i18n("FetchFeed Success") + item)
        elif "del" in FeedID:
            for item in FeedID.split(" ")[1].split(","):
                result = suno_sqlite.operate_one("update music set private=1 where aid=?", (item,))
                placeholder.success(i18n("FetchFeed Success") + item)
        elif len(FeedID) >= 36:
            FeedIDs = FeedID.split(",")
            token = get_random_token()
            fetch_feed(FeedIDs, token)
        else:
            FeedIDs = FeedID * 1
            count = 0
            for i in range(int(FeedIDs), -1, -1):
                print(i, end=" ")
                token = get_random_token()
                fetch_feed(str(i), token)
                count += 1
                if count % 5 == 0:
                    print(end="\n")
    else:
        st.session_state.FeedBtn = False

if st.session_state['continue_at'] and st.session_state['continue_clip_id']:
    StartBtn = col2.button(i18n("Extend Button"), use_container_width=True, type="primary", disabled=False)
else:
    StartBtn = col2.button(i18n("Generate"), use_container_width=True, type="primary", disabled=False)

def generate(data: schemas.CustomModeGenerateParam):
    try:
        resp = generate_music(data, get_random_token())
        return resp
    except Exception as e:
        return {"detail": str(e)}

def generate_with_song_description(data: schemas.DescriptionModeGenerateParam):
    try:
        resp = generate_music(data, get_random_token())
        return resp
    except Exception as e:
        return {"detail": str(e)}

def fetch_status(aid: str, twice=False):
    progress_text = i18n("Fetch Status Progress")
    my_bar = col2.progress(0, text=progress_text)
    percent_complete = 0
    my_bar.progress(percent_complete, text=progress_text)
    while True:
        resp = get_feed(aid, get_random_token())
        print(resp)
        print("\n")
        percent_complete = percent_complete + 1 if percent_complete >= 90 else percent_complete + 5
        if percent_complete >= 100:
            percent_complete = 100
        status = resp["detail"] if "detail" in resp else resp[0]["status"]
        if status == "running":
            progress_text = i18n("Fetch Status Running") + status
            my_bar.progress(percent_complete, text=progress_text)
        elif status == "submitted":
            progress_text = i18n("Fetch Status Running") + status
            my_bar.progress(percent_complete, text=progress_text)
        elif status == "complete":
            progress_text = i18n("Fetch Status Success") + status
            my_bar.progress(100, text=progress_text)
            check_url_available(resp[0]["video_url"], twice)
            my_bar.empty()
        elif status == "Unauthorized":
            st.session_state.token = get_random_token()
            continue
        elif status == "Not found.":
            continue
        elif status == "error":
            my_bar.empty()
        else:
            progress_text = i18n("Fetch Status Running") + status
            status = "queued"
            my_bar.progress(percent_complete, text=progress_text)
        
        result = suno_sqlite.query_one("select aid from music where aid =?", (aid,))
        print(result)
        print("\n")
        if result:
            result = suno_sqlite.operate_one("update music set data=?, updated=(datetime('now', 'localtime')), sid=?, name=?, image=?, title=?, tags=?, prompt=?, duration=?, status=? where aid =?", 
                                             (str(resp[0]), resp[0]["user_id"], resp[0]["display_name"], resp[0]["image_url"], resp[0]["title"], resp[0]["metadata"]["tags"], 
                                              resp[0]["metadata"]["gpt_description_prompt"], resp[0]["metadata"]["duration"], status, aid))
            print(local_time() + f" ***fetch_status_update aid -> {aid} status -> {status} data -> {str(resp[0])} ***\n")
        else:
            result = suno_sqlite.operate_one("insert into music (aid, data, sid, name, image, title, tags, prompt,duration, status, private) values(?,?,?,?,?,?,?,?,?,?,?)", 
                                             (str(resp[0]["id"]), str(resp[0]), resp[0]["user_id"], resp[0]["display_name"], resp[0]["image_url"], resp[0]["title"], 
                                              resp[0]["metadata"]["tags"], resp[0]["metadata"]["gpt_description_prompt"], resp[0]["metadata"]["duration"], status, st.session_state.Private))
        print(result)
        print("\n")

        if status == "complete" or status == "error":
            break

        time.sleep(10)
    if S3_WEB_SITE_URL is not None and ("s3.bitiful.net" in S3_WEB_SITE_URL or S3_WEB_SITE_URL != "https://cdn1.suno.ai"):
        resp[0]["audio_url"] = resp[0]["audio_url"].replace(S3_WEB_SITE_URL, 'https://res.sunoapi.net')
        resp[0]["video_url"] = resp[0]["video_url"].replace(S3_WEB_SITE_URL, 'https://res.sunoapi.net')
    return resp

if StartBtn:
    if not st.session_state['disabled_state']:
        if st.session_state.Custom:
            if st.session_state.Title == "":
                placeholder.error(i18n("Custom Title Error"))
            elif st.session_state.Tags == "":
                placeholder.error(i18n("Custom Tags Error"))
            elif st.session_state.Prompt == "":
                placeholder.error(i18n("Custom Prompt Error"))
            elif st.session_state['model_name'] == "":
                placeholder.error(i18n("Select Model Error"))
            else:
                data = {}
                if st.session_state.Instrumental:
                    data = {
                        "title": st.session_state.Title,
                        "tags": st.session_state.Tags if "," not in st.session_state.Tags else get_new_tags(st.session_state.Tags),
                        "prompt": "",
                        "mv": st.session_state['model_name'] if "model_name" in st.session_state else "chirp-v3-0",
                        "continue_at": None if st.session_state["continue_at"] == "" else st.session_state["continue_at"] if "continue_at" in st.session_state else None,
                        "continue_clip_id": None if st.session_state["continue_clip_id"] == "" else st.session_state["continue_clip_id"] if "continue_clip_id" in st.session_state else None,
                    }
                else:
                    data = {
                        "title": st.session_state.Title,
                        "tags": st.session_state.Tags if "," not in st.session_state.Tags else get_new_tags(st.session_state.Tags),
                        "prompt": st.session_state.Prompt,
                        "mv": st.session_state['model_name'] if "model_name" in st.session_state else "chirp-v3-0",
                        "continue_at": None if st.session_state["continue_at"] == "" else st.session_state["continue_at"] if "continue_at" in st.session_state else None,
                        "continue_clip_id": None if st.session_state["continue_clip_id"] == "" else st.session_state["continue_clip_id"] if "continue_clip_id" in st.session_state else None,
                    }
                print(data)
                print("\n")
                resp = generate(data)
                print(resp)
                print("\n")
                status = resp["status"] if "status" in resp else resp["detail"]
                if status == "running" or status == "complete":
                    st.session_state['disabled_state'] = True
                    result = suno_sqlite.operate_one("insert into music (aid, data, private) values(?,?,?)", (str(resp["clips"][0]["id"]), str(resp["clips"][0]), st.session_state.Private))

                    st.session_state['clips_0'] = str(resp["clips"][0]["id"])
                    st.session_state['clips_1'] = str(resp["clips"][1]["id"])

                    resp0 = fetch_status(resp["clips"][0]["id"], False)
                    if resp0[0]["status"] == "complete":
                        col1.audio(resp0[0]["audio_url"] + "?play=true")
                        col1.video(resp0[0]["video_url"] + "?play=true")
                        placeholder.empty()
                        col2.success(i18n("Generate Success") + resp0[0]["id"])
                    else:
                        placeholder.error(i18n("Generate Status Error") + (resp0[0]['status'] if resp0[0]['metadata']["error_message"] is None else resp0[0]['metadata']["error_message"]))
                    
                    result = suno_sqlite.operate_one("insert into music (aid, data, private) values(?,?,?)", (str(resp["clips"][1]["id"]), str(resp["clips"][1]), st.session_state.Private))

                    resp1 = fetch_status(resp["clips"][1]["id"], True)
                    if resp1[0]["status"] == "complete":
                        st.balloons()
                        col3.audio(resp1[0]["audio_url"] + "?play=true")
                        col3.video(resp1[0]["video_url"] + "?play=true")
                        placeholder.empty()
                        col2.success(i18n("Generate Success") + resp1[0]["id"])
                    else:
                        placeholder.error(i18n("Generate Status Error") + (resp1[0]['status'] if resp1[0]['metadata']["error_message"] is None else resp1[0]['metadata']["error_message"]))
                    st.session_state['disabled_state'] = False
                else:
                    placeholder.error(i18n("Generate Submit Error") + str(resp))
        else:
            if st.session_state.DescPrompt == "":
                placeholder.error(i18n("DescPrompt Error"))
            elif st.session_state['model_name'] == "":
                placeholder.error(i18n("Select Model Error"))
            else:
                data = {
                    "gpt_description_prompt": st.session_state.DescPrompt,
                    "make_instrumental": st.session_state.Instrumental,
                    "mv": st.session_state['model_name'] if "model_name" in st.session_state else "chirp-v3-0",
                    "prompt": ""
                }
                print(data)
                print("\n")
                resp = generate_with_song_description(data)
                print(resp)
                print("\n")
                status = resp["status"] if "status" in resp else resp["detail"]
                if status == "running" or status == "complete":
                    st.session_state['disabled_state'] = True
                    result = suno_sqlite.operate_one("insert into music (aid, data, private) values(?,?,?)", (str(resp["clips"][0]["id"]), str(resp["clips"][0]), st.session_state.Private))

                    st.session_state['clips_0'] = str(resp["clips"][0]["id"])
                    st.session_state['clips_1'] = str(resp["clips"][1]["id"])

                    resp0 = fetch_status(resp["clips"][0]["id"], False)
                    if resp0[0]["status"] == "complete":
                        col1.audio(resp0[0]["audio_url"] + "?play=true")
                        col1.video(resp0[0]["video_url"] + "?play=true")
                        placeholder.empty()
                        st.session_state.DescPrompt = ""
                        col2.success(i18n("Generate Success") + resp0[0]["id"])
                    else:
                        placeholder.error(i18n("Generate Status Error") + (resp0[0]['status'] if resp0[0]['metadata']["error_message"] is None else resp0[0]['metadata']["error_message"]))

                    result = suno_sqlite.operate_one("insert into music (aid, data, private) values(?,?,?)", (str(resp["clips"][1]["id"]), str(resp["clips"][1]), st.session_state.Private))
                    
                    resp1 = fetch_status(resp["clips"][1]["id"], True)
                    if resp1[0]["status"] == "complete":
                        st.balloons()
                        col3.audio(resp1[0]["audio_url"] + "?play=true")
                        col3.video(resp1[0]["video_url"] + "?play=true")
                        placeholder.empty()
                        st.session_state.DescPrompt = ""
                        col2.success(i18n("Generate Success") + resp1[0]["id"])
                    else:
                        placeholder.error(i18n("Generate Status Error") + (resp1[0]['status'] if resp1[0]['metadata']["error_message"] is None else resp1[0]['metadata']["error_message"]))
                    st.session_state['disabled_state'] = False
                else:
                    placeholder.error(i18n("Generate Submit Error") + str(resp))
    else:
        if st.session_state['clips_0'] != "":
            resp0 = fetch_status(st.session_state['clips_0'], False)
            if resp0[0]["status"] == "complete":
                col1.audio(resp0[0]["audio_url"] + "?play=true")
                col1.video(resp0[0]["video_url"] + "?play=true")
                placeholder.empty()
                col2.success(i18n("Generate Success") + resp0[0]["id"])
            else:
                placeholder.error(i18n("Generate Status Error") + (resp0[0]['status'] if resp0[0]['metadata']["error_message"] is None else resp0[0]['metadata']["error_message"]))

        if st.session_state['clips_1'] != "":
            resp1 = fetch_status(st.session_state['clips_1'], True)
            if resp1[0]["status"] == "complete":
                st.balloons()
                col3.audio(resp1[0]["audio_url"] + "?play=true")
                col3.video(resp1[0]["video_url"] + "?play=true")
                placeholder.empty()
                col2.success(i18n("Generate Success") + resp1[0]["id"])
            else:
                placeholder.error(i18n("Generate Status Error") + (resp1[0]['status'] if resp1[0]['metadata']["error_message"] is None else resp1[0]['metadata']["error_message"]))

# Hide right menu and footer and adjust padding to avoid header overlap
hide_streamlit_style = """
<style>
#MainMenu {display: none;}
footer {display: none;}
.eczjsme10 {display: none;}
#root > div:nth-child(1) > div > div > div > div > section > div {padding-top: 3rem; z-index: 1;}
.st-bb {background-color: white !important;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# Artalk comments initialization
hide_streamlit_style1 = """
<div id="Comments"></div>
<div style="display:none">
<link href="https://sunoapi.net/dist/Artalk.css" rel="stylesheet" />
<script src="https://sunoapi.net/dist/Artalk.js"></script>
<div style="font-size: 12px;font-family: inherit; color: #697182;justify-content: center; align-items: center; word-break: break-word; text-align: center;padding-right: 15px;">本页浏览量 <span id="ArtalkPV">Loading...</span> 次</div>
<div id="Comments"></div>
<script>
  Artalk.init({
  el:        '#Comments',
  pageKey:   '/',
  pageTitle: '音乐歌曲创作'
  server:    'https://sunoapi.net',
  site:      'SunoAPI AI Music Generator',
  })
</script>
</div>
"""
with col2:
    st.components.v1.html(hide_streamlit_style1, height=30)

components.iframe("https://sunoapi.net/analytics.html", height=0)