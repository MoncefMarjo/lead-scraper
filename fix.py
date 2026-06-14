content = open('main.py').read()
old = "Service(C:\\Users\\Admin\\Desktop\\Lead-Scraper\\chromedriver.exe)"
new = "Service(r'C:\\Users\\Admin\\Desktop\\Lead-Scraper\\chromedriver.exe')"
content = content.replace(old, new)
open('main.py', 'w').write(content)
print('Fixed!')