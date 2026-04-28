# Unit Testing Framework Instructions

We are using this repository to develop the Car Flipper Project. We have implemented a testing framework to follow Test Driven Development principles and ensure the reliability of the core valuation logic.

## How to Pull the Project
To clone the repository to your local machine or server execute the following command in your terminal:

git clone https://github.com/qeax/CSS360A_PROJECT.git
cd CSS360A_PROJECT

## Installation of Requirements
We have selected Pytest as the primary testing framework for this Python backend. You need to install it to run the test suite.

1. Ensure you have Python 3.9 or higher installed.
2. Install Pytest using the following command:
   python3 -m pip install pytest

## Running the Test Suite
To execute the automated tests navigate to the project root directory and run this command:

python3 -m pytest backend/test_analyzer.py

## Current Test Status and TDD Red Phase
Please note that the test suite is currently expected to fail with 7 failures.

We are strictly following the Red Green Refactor cycle of TDD. We wrote the test cases in test_analyzer.py first to define the requirements for the search validators and profit calculation engine. Because we have not yet implemented the functional code the tests will trigger an AssertionError. 

This is a deliberate part of our project management strategy. It confirms that the testing framework is correctly operational and provides a clear technical roadmap for the upcoming implementation phase.