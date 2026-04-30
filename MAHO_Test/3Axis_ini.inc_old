[DISPLAY]
DISPLAY = gmoccapy
MAX_LINEAR_VELOCITY = 1

[TASK]
TASK = milltask
CYCLE_TIME = 0.001

[RS274NGC]
# NoneType object has no attribute 'rfind'
PARAMETER_FILE = Maho400E.var

[EMCIO]
EMCIO = io
CYCLE_TIME = 0.100
TOOL_TABLE = tools.tbl

[EMCMOT]
EMCMOT = motmod
SERVO_PERIOD = 1000000

[SPINDLE_0]
MAX_FORWARD_VELOCITY = 4500
INCREMENT = 10

# =========================================
# Axis X
# =========================================
[AXIS_X]
MAX_VELOCITY = 100.0
MAX_ACCELERATION = 500.0

[JOINT_0]
TYPE = LINEAR
HOME_SEQUENCE = 0
HOME_SEARCH_VEL = 20.0
HOME_LATCH_VEL = 1.0

# PID Parameters
P = 10.0
I = 0.0
D = 0.1
FF0 = 0.0
FF1 = 1.0
FF2 = 0.0
DEADBAND = 0.005
MAX_OUTPUT = 10.0

# Scaling
# OUTPUT_SCALE: Usually corresponds to the maximum voltage (e.g. 10V for EL4034)
OUTPUT_SCALE = 10.0
# ENCODER_SCALE: Encoder increments per millimeter of travel
ENCODER_SCALE = 1000.0

# Following error limits (Closed Loop)
FERROR = 1.0
MIN_FERROR = 0.1


# =========================================
# Axis Y
# =========================================
[AXIS_Y]
MAX_VELOCITY = 100.0
MAX_ACCELERATION = 500.0

[JOINT_1]
TYPE = LINEAR
HOME_SEQUENCE = 1
HOME_SEARCH_VEL = 20.0
HOME_LATCH_VEL = 1.0

# PID Parameters
P = 10.0
I = 0.0
D = 0.1
FF0 = 0.0
FF1 = 1.0
FF2 = 0.0
DEADBAND = 0.005
MAX_OUTPUT = 10.0

# Scaling
OUTPUT_SCALE = 10.0
ENCODER_SCALE = 1000.0

# Following error limits (Closed Loop)
FERROR = 1.0
MIN_FERROR = 0.1


# =========================================
# Axis Z
# =========================================
[AXIS_Z]
MAX_VELOCITY = 50.0
MAX_ACCELERATION = 250.0

[JOINT_2]
TYPE = LINEAR
HOME_SEQUENCE = 2
HOME_SEARCH_VEL = 10.0
HOME_LATCH_VEL = 1.0

# PID Parameters
P = 15.0
I = 0.0
D = 0.1
FF0 = 0.0
FF1 = 1.0
FF2 = 0.0
DEADBAND = 0.005
MAX_OUTPUT = 10.0

# Scaling
OUTPUT_SCALE = 10.0
ENCODER_SCALE = 1000.0

# Following error limits (Closed Loop)
FERROR = 1.0
MIN_FERROR = 0.1
