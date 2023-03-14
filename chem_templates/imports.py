import os
from typing import Union, Optional, Callable, Tuple, Any
from collections import OrderedDict, defaultdict
from itertools import permutations, product, chain, islice
import re
import random
import warnings
import time
import pickle
import json
from multiprocessing import Pool
from functools import partial

# external
import numpy as np
import datasets