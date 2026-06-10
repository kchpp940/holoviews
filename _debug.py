
import warnings; warnings.filterwarnings('ignore')
import holoviews as hv
import numpy as np
from holoviews.core.hover import HoverResolver

hv.extension('bokeh')
xs = np.arange(5).astype(float)
ys = xs ** 2
scatter = hv.Scatter((xs, ys), kdims=['x'], vdims=['y'],
    hover_fields=['x', 'y']).opts(tools=['hover'])

renderer = hv.renderer('bokeh')
plot = renderer.get_plot(scatter)
print('plot type:', type(plot).__name__)
print('has element:', hasattr(plot, 'element'))
print('has current_frame:', hasattr(plot, 'current_frame'))
if hasattr(plot, 'current_frame'):
    print('current_frame:', plot.current_frame)
    print('  hover_fields:', plot.current_frame.hover_fields)

# Try multiple ways
for attr in ['element', 'current_frame', '_element', 'hmap']:
    if hasattr(plot, attr):
        val = getattr(plot, attr)
        if hasattr(val, 'hover_fields'):
            print(f'{attr}.hover_fields:', val.hover_fields)

meta = renderer._collect_hover_metadata(plot)
print('collect result:', meta is not None)

# Direct __call__
data, info = renderer(scatter, fmt='html')
print('info keys:', list(info.keys()))
print('holoviews:hover in info:', 'holoviews:hover' in info)
print('last_hover_metadata:', renderer.last_hover_metadata is not None)

# Also test with png
data2, info2 = renderer(scatter, fmt='png')
print('png info keys:', list(info2.keys()))
print('png has hover:', 'holoviews:hover' in info2)
