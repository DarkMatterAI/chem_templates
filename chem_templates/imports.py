import os
from typing import Union, Optional, Callable, Tuple, Any
from collections import OrderedDict, defaultdict
from itertools import permutations
import re
import random
import warnings
import time
import pickle
import json
from multiprocessing import Pool

# external
import numpy as np
import datasets