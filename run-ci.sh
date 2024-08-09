if [ -d .pytest_cache ]; then rm -rf .pytest_cache; fi
if [ -d htmlcov ]; then rm -rf htmlcov; fi
if [ -d icloud ]; then rm -rf icloud; fi
if [ -d session_data ]; then rm -rf session_data; fi
if [ -f icloud.log ]; then rm -f icloud.log; fi
echo "Ruffing ..." &&
    ruff check --fix &&
    echo "Testing ..." &&
    ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest &&
    echo "Reporting ..." &&
    allure generate --clean &&
    echo "Done."
