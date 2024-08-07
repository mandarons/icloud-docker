import json
import os
import shutil
import xml.etree.ElementTree as ET

import requests

badges_directory = "./badges"

with open("./allure-report/widgets/summary.json") as f:
    test_data = json.load(f)
    test_result = test_data["statistic"]["total"] == test_data["statistic"]["passed"]

coverage_result = float(ET.parse("./coverage.xml").getroot().attrib["line-rate"]) * 100.0

if os.path.exists(badges_directory) and os.path.isdir(badges_directory):
    shutil.rmtree(badges_directory)
    os.mkdir(badges_directory)
else:
    os.mkdir(badges_directory)

url_data = "passing&color=brightgreen" if test_result else "failing&color=critical"
response = requests.get("https://img.shields.io/static/v1?label=Tests&message=" + url_data)
with open(badges_directory + "/tests.svg", "w") as f:
    f.write(response.text)
url_data = "brightgreen" if coverage_result == 100.0 else "critical"
response = requests.get(f"https://img.shields.io/static/v1?label=Coverage&message={coverage_result}%&color={url_data}")
with open(badges_directory + "/coverage.svg", "w") as f:
    f.write(response.text)
