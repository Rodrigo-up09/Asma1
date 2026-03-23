# ASMA - Agent-based System

A Python-based agent system built with SPADE (Smart Python multi-Agent Development Environment).

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- OpenSSL (for XMPP communication)

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Rodrigo-up09/Asma1.git
cd project1
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## Project Structure

```
project1/
├── main.py                 # Main entry point
├── requirements.txt        # Project dependencies
├── agents/
│   └── start.py           # Agent definitions and setup
└── README.md              # This file
```

## Running the Project

### Activate Virtual Environment

```bash
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### Run the Main Application

```bash
python main.py
```

This will:
1. Create a DummyAgent with JID `dummy@localhost`
2. Start the agent and display "Hello World! I'm agent dummy@localhost"
3. Run the agent server








