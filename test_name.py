from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import time

s = Service(r'C:\Users\Admin\Desktop\Lead-Scraper\chromedriver.exe')
d = webdriver.Chrome(service=s)
d.get('https://www.google.com/maps/search/Kandbaz+Paris')
time.sleep(5)
elements = d.find_elements(By.XPATH, '//a[contains(@href,"/maps/place/")]')
if elements:
    d.get(elements[0].get_attribute('href'))
    time.sleep(4)
    try:
        name = d.find_element(By.XPATH, '//h1').text
        print('NAME:', name)
    except:
        print('h1 not found')
d.quit()