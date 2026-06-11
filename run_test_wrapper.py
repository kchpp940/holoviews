import sys
import os
import warnings

warnings.filterwarnings('ignore')
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', message='.*oneOf.*')
warnings.filterwarnings('ignore', message='.*one_of.*')

os.environ['PYTHONWARNINGS'] = 'ignore'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_to_file.py')).read())
