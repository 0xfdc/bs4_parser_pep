import logging
import re
from collections import defaultdict
from urllib.parse import urljoin

import requests_cache
from bs4 import BeautifulSoup
from tqdm import tqdm

from configs import configure_argument_parser, configure_logging
from constants import MAIN_DOC_URL, PEPS_URL, EXPECTED_STATUS, DOWNLOADS_DIR
from outputs import control_output, file_output
from utils import get_response, find_tag, select_tags, select_tag


def get_soup(session, url):
    response = get_response(session, url)
    if response is None:
        logging.error(f'Ошибка при запросе к {url}', stack_info=True)
        return
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, features='lxml')
    return soup


def whats_new(session):
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')
    soup = get_soup(session, whats_new_url)
    sections_by_python = select_tags(
        soup,
        '#what-s-new-in-python div.toctree-wrapper li.toctree-l1'
    )
    results = [('Ссылка на статью', 'Заголовок', 'Редактор, автор')]
    for section in tqdm(sections_by_python):
        version_a_tag = find_tag(section, 'a')
        href = version_a_tag['href']
        version_link = urljoin(whats_new_url, href)
        soup = get_soup(session, version_link)
        results.append(
            (
                version_link,
                find_tag(soup, 'h1').text,
                find_tag(soup, 'dl').text.replace('\n', ' ')
            )
        )

    return results


def latest_versions(session):
    soup = get_soup(session, MAIN_DOC_URL)
    ul_tags = select_tags(soup, 'div.sphinxsidebarwrapper ul')
    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
    else:
        raise ValueError('Ничего не нашлось')
    results = [('Ссылка на документацию', 'Версия', 'Статус')]
    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        text_match = re.search(pattern, a_tag.text)
        if text_match is not None:
            version, status = text_match.groups()
        else:
            version, status = a_tag.text, ''
        results.append(
            (a_tag['href'], version, status)
        )
    return results


def download(session):
    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')
    soup = get_soup(session, downloads_url)
    pdf_a4_link = select_tag(
        soup,
        'div[role=main] table.docutils a[href$=.zip]'
    )['href']
    archive_url = urljoin(downloads_url, pdf_a4_link)
    filename = archive_url.split('/')[-1]
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    archive_path = DOWNLOADS_DIR / filename
    response = session.get(archive_url)
    with open(archive_path, 'wb') as file:
        file.write(response.content)
    logging.info(f'Архив был загружен и сохранён: {archive_path}')


def pep(session):
    soup = get_soup(session, PEPS_URL)
    pep_rows = select_tags(soup, 'tbody > tr')
    pep_statuses_count = defaultdict(int)
    pattern = r'Status:\n(?P<status>\w+)'
    error_messages = list()
    for pep_row in tqdm(pep_rows):
        if len(find_tag(pep_row, 'abbr').text) > 1:
            pep_list_status = find_tag(pep_row, 'abbr').text[1:]
        else:
            pep_list_status = ''
        pep_link = find_tag(pep_row, 'a')['href']
        pep_page_url = urljoin(PEPS_URL, pep_link)
        soup = get_soup(session, pep_page_url)
        pep_page_info = find_tag(
            soup,
            'dl',
            {'class': 'rfc2822 field-list simple'}
        )
        match = re.search(pattern, pep_page_info.text)
        pep_status = match.group('status')
        pep_statuses_count[pep_status] += 1
        if pep_status not in EXPECTED_STATUS[pep_list_status]:
            error_messages.append(
                '\n'
                'Несовпадающие статусы:\n'
                f'{pep_page_url}\n'
                f'Статус в карточке: {pep_status}\n'
                f'Ожидаемые статусы: '
                f'{EXPECTED_STATUS[pep_list_status]}\n'
            )
    for error_message in error_messages:
        logging.info(error_message)
    return [
        ('Статус', 'Количество'),
        *pep_statuses_count.items(),
        ('Всего', sum(pep_statuses_count.values())),
    ]


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep
}


def main():
    try:
        configure_logging()
        logging.info('Парсер запущен!')
        arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
        args = arg_parser.parse_args()
        logging.info(f'Аргументы командной строки: {args}')
        session = requests_cache.CachedSession()
        if args.clear_cache:
            session.cache.clear()
        parser_mode = args.mode
        results = MODE_TO_FUNCTION[parser_mode](session)

        if results is not None:
            if parser_mode == 'pep':
                file_output(results, args)
            else:
                control_output(results, args)
    except Exception as error:
        logging.error(f'Ошибка: {error}')
    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
