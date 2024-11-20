import logging
import re
from urllib.parse import urljoin

import requests_cache
from bs4 import BeautifulSoup
from tqdm import tqdm

from configs import configure_argument_parser, configure_logging
from constants import BASE_DIR, MAIN_DOC_URL, PEPS_URL, EXPECTED_STATUS
from outputs import control_output, file_output
from utils import get_response, find_tag


def whats_new(session):
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')
    response = get_response(session, whats_new_url)
    if response is None:
        return
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, features='lxml')

    main_div = find_tag(soup, 'section', attrs={'id': 'what-s-new-in-python'})
    div_with_ul = find_tag(main_div, 'div', attrs={'class': 'toctree-wrapper'})
    sections_by_python = div_with_ul.find_all(
        'li', attrs={'class': 'toctree-l1'}
    )
    results = [('Ссылка на статью', 'Заголовок', 'Редактор, автор')]
    for section in tqdm(sections_by_python):
        version_a_tag = find_tag(section, 'a')
        href = version_a_tag['href']
        version_link = urljoin(whats_new_url, href)
        response = get_response(session, version_link)
        if response is None:
            continue
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, features='lxml')
        h1 = find_tag(soup, 'h1')
        dl = find_tag(soup, 'dl')
        dl_text = dl.text.replace('\n', ' ')
        results.append(
            (version_link, h1.text, dl_text)
        )

    return results


def latest_versions(session):
    response = get_response(session, MAIN_DOC_URL)
    if response is None:
        return
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, features='lxml')
    sidebar = find_tag(soup, 'div', {'class': 'sphinxsidebarwrapper'})
    ul_tags = sidebar.find_all('ul')
    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
    else:
        raise Exception('Ничего не нашлось')
    results = [('Ссылка на документацию', 'Версия', 'Статус')]
    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        link = a_tag['href']
        text_match = re.search(pattern, a_tag.text)
        if text_match is not None:
            version, status = text_match.groups()
        else:
            version, status = a_tag.text, ''
        results.append(
            (link, version, status)
        )
    return results


def download(session):
    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')
    response = get_response(session, downloads_url)
    if response is None:
        return
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, features='lxml')
    main_div = find_tag(soup, 'div', {'role': 'main'})
    table = find_tag(main_div, 'table', {'class': 'docutils'})
    pdf_a4_tag = find_tag(table, 'a', {'href': re.compile(r'.+pdf-a4\.zip$')})
    pdf_a4_link = pdf_a4_tag['href']
    archive_url = urljoin(downloads_url, pdf_a4_link)
    filename = archive_url.split('/')[-1]
    downloads_dir = BASE_DIR / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / filename
    response = session.get(archive_url)
    with open(archive_path, 'wb') as file:
        file.write(response.content)
    logging.info(f'Архив был загружен и сохранён: {archive_path}')


def pep(session):
    response = get_response(session, PEPS_URL)
    if response is None:
        return
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, features='lxml')
    main_section = find_tag(soup, 'section', {'id': 'index-by-category'})
    tables = main_section.find_all('table')
    for table in tables:
        table.thead.decompose()
    pep_rows = main_section.find_all('tr')
    pep_statuses_count = dict()
    pep_total_count = 0
    pattern = r'Status:\n(?P<status>\w+)'
    results = [('Статус', 'Количество')]
    for pep_row in tqdm(pep_rows):
        pep_total_count += 1
        if len(find_tag(pep_row, 'abbr').text) > 1:
            pep_list_status = find_tag(pep_row, 'abbr').text[1:]
        else:
            pep_list_status = ''
        pep_link = find_tag(pep_row, 'a')['href']
        pep_page_url = urljoin(PEPS_URL, pep_link)
        response = get_response(session, pep_page_url)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, features='lxml')
        pep_page_info = find_tag(
            soup,
            'dl',
            {'class': 'rfc2822 field-list simple'}
        )
        match = re.search(pattern, pep_page_info.text)
        pep_status = match.group('status')
        pep_statuses_count[pep_status] = pep_statuses_count.get(
            pep_status,
            0
        ) + 1
        if pep_status not in EXPECTED_STATUS[pep_list_status]:
            logging.info(
                '\n'
                'Несовпадающие статусы:\n'
                f'{pep_page_url}\n'
                f'Статус в карточке: {pep_status}\n'
                f'Ожидаемые статусы: '
                f'{EXPECTED_STATUS[pep_list_status]}\n'
            )
    for status in pep_statuses_count:
        results.append((status, pep_statuses_count[status]))
    results.append(('Total', pep_total_count))
    return results


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep
}


def main():
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
    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
