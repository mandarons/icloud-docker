if [ -d .pytest_cache ]; then rm -rf .pytest_cache; fi
if [ -d htmlcov ]; then rm -rf htmlcov; fi
if [ -f icloud.log ]; then rm -f icloud.log; fi
echo "Linting ..." &&
    pylint src/ tests/ &&
    echo "Testing ..." &&
    pytest &&
    echo "Reporting ..." &&
    allure generate --clean &&
    echo "Done."
