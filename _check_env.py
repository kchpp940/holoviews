import warnings
warnings.filterwarnings("ignore")
import sys
print("Python path:", sys.path[:3])
print()

try:
    import holoviews as hv
    print("hv version:", hv.__version__)
    print("Store.loaded_backends:", hv.Store.loaded_backends())
except Exception as e:
    print("hv import error:", e)
    import traceback
    traceback.print_exc()
print()

try:
    from holoviews.plotting import bokeh
    print("bokeh plotting import OK")
except Exception as e:
    print("bokeh plotting import error:", e)

print()
try:
    from holoviews.plotting import mpl
    print("mpl plotting import OK")
except Exception as e:
    print("mpl plotting import error:", e)
