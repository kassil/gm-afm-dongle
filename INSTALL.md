560  # create and activate a virtual environment
  561  python3 -m venv venv
  562  source venv/bin/activate
  563  # install dependencies
  564  pip install click python-can
  565  # verify
  566  pip show click python-can
  567  ls
  568  python tester_
  569  python tester_tool.py 
  570  nano tester_tool.py 
  571  pip install click python-can python_ics
