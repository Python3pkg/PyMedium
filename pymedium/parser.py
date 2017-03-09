#!/usr/bin/python3
# -*- coding: utf8 -*-
import re
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

from .model import User, Post, Publication, Tag, Image, OutputFormat, to_dict

__author__ = 'enginebai'

ROOT_URL = "https://medium.com/"
HTML_PARSER = "html.parser"


def parse_user(payload):
    user_dict = payload["payload"]["user"]
    user_id = user_dict["userId"]
    user = User(user_id)
    username = user_dict["username"]
    display_name = user_dict["name"]
    avatar = user_dict["imageId"]
    bio = user_dict["bio"]
    twitter_name = user_dict["twitterScreenName"]
    facebook_id = user_dict["facebookAccountId"]

    user_meta_dict = payload["payload"]["userMeta"]
    ref_dict = payload["payload"]["references"]

    # interest_tags = user_meta_dict["interestTags"]
    # user.interest_tags = parse_tags(interest_tags)
    # author_tags = user_meta_dict["authorTags"]
    # user.author_tags = parse_tags(author_tags)

    publication_ids = user_meta_dict["collectionIds"]
    if publication_ids is not None and len(publication_ids) > 0:
        publication_list = []
        for pub_id in publication_ids:
            publication_dict = ref_dict["Collection"][pub_id]
            publication = Publication(pub_id)
            publication.name = publication_dict["name"]
            publication.unique_slug = publication_dict["slug"]
            publication.description = publication_dict["description"]
            image_dict = publication_dict["image"]
            publication.image = parse_images(image_dict)
            logo_dict = publication_dict["logo"]
            publication.logo = parse_images(logo_dict)
            publication.follower_count = publication_dict["metadata"]["followerCount"]
            publication_list.append(to_dict(publication))
        user.publications = publication_list

    stats_dict = ref_dict["SocialStats"][user_id]
    following_count = stats_dict["usersFollowedCount"]
    followby_count = stats_dict["usersFollowedByCount"]

    user.user_id = user_id
    user.username = username
    user.display_name = display_name
    user.avatar = avatar
    user.bio = bio
    user.twitter = twitter_name
    user.facebook = facebook_id
    user.following_count = following_count
    user.followedby_count = followby_count

    return to_dict(user)


def parse_post(payload):
    return parse_post_information(payload, ("payload", "references", "Post"))


def parse_post_information(payload, post_detail_keys):
    if post_detail_keys is None:
        return
    post_list_payload = payload
    for key in post_detail_keys:
        post_list_payload = post_list_payload.get(key)

    def parse_post_dict(post_dict):
        post = Post(post_id)
        unique_slug = post_dict["uniqueSlug"]
        title = post_dict["title"]
        post_date = post_dict["createdAt"]

        # print(post_date)
        publication_id = post_dict["approvedHomeCollectionId"]

        url = ROOT_URL
        ref_dict = payload["payload"]["references"]
        if publication_id is not None and publication_id:
            publication_dict = ref_dict["Collection"][publication_id]
            # custom publication domain
            if "domain" in publication_dict and publication_dict["domain"]:
                url = "https://" + publication_dict["domain"]
            else:
                # simple publication
                url += publication_dict["slug"]
        else:
            # personal post, no publication
            creator_id = post_dict["creatorId"]
            username = ref_dict["User"][creator_id]["username"]
            url += "@{username}".format(username=username)
        url += u"/{path}".format(path=unique_slug)

        virtual_dict = post_dict["virtuals"]
        recommend_count = virtual_dict["recommends"]
        response_count = virtual_dict["responsesCreatedCount"]
        read_time = virtual_dict["readingTime"]
        word_count = virtual_dict["wordCount"]
        image_count = virtual_dict["imageCount"]
        preview_image = virtual_dict["previewImage"]
        # post_tags = virtual_dict["tags"]
        # post.post_tags = parse_tags(post_tags)

        post.unique_slug = unique_slug
        post.title = title
        post.post_date = post_date
        post.url = url
        post.recommend_count = recommend_count
        post.response_count = response_count
        post.read_time = read_time
        post.word_count = word_count
        post.image_count = image_count
        post.preview_image = parse_images(preview_image)

        # print("{id}, {title}".format(id=post_id, title=title))
        # print("{recommend}, {response}, {read}".format(
        # recommend=recommend_count, response=response_count, read=read_time))
        return to_dict(post)

    post_list = []
    # payload -> references -> Post
    if type(post_list_payload) is dict:
        for post_id in post_list_payload.keys():
            post_dict = post_list_payload.get(post_id)
            post_list.append(parse_post_dict(post_dict))
    # payload -> value
    elif type(post_list_payload) is list:
        for post_dict in post_list_payload:
            post_list.append(parse_post_dict(post_dict))

    return post_list


def parse_tags(tags_list_dict):
    if tags_list_dict is not None and len(tags_list_dict) > 0:
        tags_list = []
        for tag_dict in tags_list_dict:
            tag = Tag()
            tag.unique_slug = tag_dict["slug"]
            tag.name = tag_dict["name"]
            tag.post_count = tag_dict["postCount"]
            metadata_dict = tag_dict["metadata"]
            if metadata_dict is not None:
                tag.follower_count = metadata_dict["followerCount"]
            tags_list.append(to_dict(tag))
        return tags_list


def parse_images(image_dict):
    if image_dict is not None:
        image = Image(image_dict["imageId"] if "imageId" in image_dict else image_dict["id"])
        image.original_width = image_dict["originalWidth"]
        image.original_height = image_dict["originalHeight"]
        image.url = u"https://cdn-images-1.medium.com/fit/t/{width}/{height}/{id}" \
            .format(width=image.original_width,
                    height=image.original_height,
                    id=image.image_id)
        return to_dict(image)


def parse_post_detail(post_url, output_format):
    with webdriver.Remote(desired_capabilities=DesiredCapabilities.HTMLUNITWITHJS) as driver:
        driver.get(post_url)
        content_elements = driver.find_element_by_class_name("postArticle-content")
        content_tags = BeautifulSoup(content_elements.get_attribute("innerHTML"), HTML_PARSER).find_all()

        if output_format == OutputFormat.MARKDOWN.value:
            return to_markdown(content_tags, driver)
        else:
            return ""


def strip_space(text, trim_space=True):
    text = re.sub(r'\s+', ' ', text)
    if trim_space:
        return text.strip()
    else:
        return text


def to_markdown(medium_tag, driver):
    text = strip_space(medium_tag.text)
    if medium_tag.name == 'h3':
        return '\n## {}'.format(text)
    elif medium_tag.name == 'h4':
        return '\n### {}'.format(text)
    elif medium_tag.name == 'p':  # text paragraph
        # find style, link inside a paragraph
        plain_text = ''
        for child in medium_tag.children:
            if child.name is None:
                if len(strip_space(child.string)) > 0:
                    plain_text += strip_space(child.string)
            else:
                content = strip_space(child.text)
                if child.name == 'strong':
                    plain_text += " **{0}** ".format(content)
                elif child.name == 'em':
                    plain_text += " _{0}_ ".format(content)
                elif child.name == 'a':
                    plain_text += " [{0}]({1}) ".format(content, child['href'])
                elif child.name == 'code' or child.name == '':
                    plain_text += " `{0}` ".format(content)
        return plain_text
    elif medium_tag.name == 'figure':  # image and comment
        img_tag = medium_tag.find('img', class_='progressiveMedia-image')
        if img_tag is not None and img_tag.has_attr('data-src'):
            figcaption_tag = medium_tag.find('figcaption')
            if figcaption_tag is not None:
                return '\n![{0}]({1})'.format(strip_space(figcaption_tag.text),
                                              img_tag['data-src'])
            else:
                return '\n![]({})'.format(img_tag['data-src'])
    elif medium_tag.name == 'blockquote':  # quote
        return '> {}\n'.format(strip_space(medium_tag.text))
    elif medium_tag.name == 'ul':
        li_tags = medium_tag.find_all('li')
        # use newline to join several item lines
        list_text = '\n'.join(['* {}'.format(strip_space(li.text)) for li in li_tags])
        return "\n" + list_text + "\n"
    elif medium_tag.name == 'ol':
        li_tags = medium_tag.find_all('li')
        # use newline to join several item lines
        list_text = '\n'.join(['{0}. {1}'.format(i + 1, strip_space(li_tags[i].text))
                               for i in range(len(li_tags))])
        return "\n" + list_text + "\n"
    elif medium_tag.name == 'pre':  # code block (not inline code or embed code)
        code_block = ''
        code_tags = medium_tag.prettify().split('<br/>')
        for i in range(len(code_tags)):
            t = BeautifulSoup(code_tags[i], HTML_PARSER)
            code = re.sub(r'\r\n(\s{10})', '', t.text).replace('\n', '')
            code_block += '{}\n'.format(code)
            # print(i, code)
        return '\n```\n{}```\n\n'.format(code_block)
    elif medium_tag.name == 'hr':
        return '\n----\n'
    elif medium_tag.name == 'iframe':
        # gist, video, github, link...etc.
        iframe_url = ROOT_URL + medium_tag['data-src']
        try:
            driver.get(iframe_url)
            iframe_content = BeautifulSoup(driver.page_source, HTML_PARSER)
            tag = iframe_content.find('div', class_='gist-meta')
            if tag is not None:
                gist_raw_link = tag.find('a', href=re.compile(r'gist.github.com(.*)/raw/'))
                if gist_raw_link is not None:
                    # print(gist_raw_link['href'])`
                    req = requests.get(gist_raw_link['href'])
                    if req.status_code == 200:
                        code_html = BeautifulSoup(req.content, HTML_PARSER)
                        return '\n```\n{}\n```\n\n'.format(code_html.prettify())
        except RuntimeError:
            print("[ERROR] Failed to parse the embed link.")
            # print(e)

    elif medium_tag.name == 'a':
        if medium_tag.has_attr('class') and 'markup--mixtapeEmbed-anchor' in medium_tag['class']:
            link_text_tag = medium_tag.strong
            if link_text_tag is not None:
                text = strip_space(link_text_tag.text)
            url = medium_tag.get('href')
            if 'https://medium.com/r/?url=' in url:
                url = url.split('url=')[1]
                url = unquote(url)
            return '\n[{}]({})\n'.format(text, url)
    else:
        return None
