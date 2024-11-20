from requests import RequestException
from exceptions import ParserFindTagException, ParserSelectTagsException


def get_response(session, url):
    try:
        response = session.get(url)
        response.encoding = 'utf-8'
        return response
    except RequestException:
        raise ConnectionError(f'Ошибка при запросе страницы {url}')


def find_tag(soup, tag, attrs=None):
    searched_tag = soup.find(tag, attrs=(attrs or {}))
    if searched_tag is None:
        error_msg = f'Не найден тег {tag} {attrs}'
        raise ParserFindTagException(error_msg)
    return searched_tag


def select_tags(soup, selector):
    selected_tags = soup.select(selector)
    if selected_tags is None:
        error_msg = f'Не найдены теги соответствующие селектору {selector}'
        raise ParserSelectTagsException(error_msg)
    return selected_tags


def select_tag(soup, selector):
    selected_tag = soup.select_one(selector)
    if selected_tag is None:
        error_msg = f'Не найден тег соответствующие селектору {selector}'
        raise ParserSelectTagsException(error_msg)
    return selected_tag
