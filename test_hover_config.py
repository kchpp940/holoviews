
import holoviews as hv
import numpy as np

print('=== 测试 1: 基本参数存在性 ===')
from holoviews.core.dimension import Dimensioned
print('hover_fields param:', hasattr(Dimensioned, 'hover_fields'))
print('hover_formatters param:', hasattr(Dimensioned, 'hover_formatters'))
print('hover_aliases param:', hasattr(Dimensioned, 'hover_aliases'))

print()
print('=== 测试 2: 创建 Scatter 元素 ===')
xs = np.linspace(0, 10, 20)
ys = xs ** 2
zs = xs * 2
scatter = hv.Scatter((xs, ys, zs), kdims=['x'], vdims=['y', 'z'])
print('元素类型:', type(scatter).__name__)
print('kdims:', [d.name for d in scatter.kdims])
print('vdims:', [d.name for d in scatter.vdims])

print()
print('=== 测试 3: 默认 hover_fields ===')
default_fields = scatter._get_hover_fields()
print('默认字段数:', len(default_fields))
print('默认字段:', [scatter._resolve_hover_field_name(f) for f in default_fields])

print()
print('=== 测试 4: 自定义 hover_fields ===')
scatter2 = hv.Scatter(
    (xs, ys, zs), 
    kdims=['x'], 
    vdims=['y', 'z'],
    hover_fields=['x', 'y']
)
custom_fields = scatter2._get_hover_fields()
print('自定义字段数:', len(custom_fields))
print('自定义字段:', [scatter2._resolve_hover_field_name(f) for f in custom_fields])

print()
print('=== 测试 5: hover_aliases ===')
scatter3 = hv.Scatter(
    (xs, ys, zs), 
    kdims=['x'], 
    vdims=['y', 'z'],
    hover_fields=['x', 'y', 'z'],
    hover_aliases={'x': 'X 坐标', 'y': 'Y 平方值', 'z': 'Z 倍数'}
)
for f in scatter3._get_hover_fields():
    name = scatter3._resolve_hover_field_name(f)
    label = scatter3._get_hover_field_label(f)
    print(f'字段 {name} -> 标签: {label}')

print()
print('=== 测试 6: hover_data ===')
hover_data = scatter3._get_hover_data()
print('hover_data keys:', list(hover_data.keys()))
for k, v in hover_data.items():
    print(f'  {k}: {v[:3]}... (共 {len(v)} 个值)')

print()
print('=== 测试 7: hover_tooltips_spec ===')
tooltips = scatter3._get_hover_tooltips_spec()
print('tooltips:', tooltips)

print()
print('=== 测试 8: dim() 表达式 ===')
from holoviews.util.transform import dim
scatter4 = hv.Scatter(
    (xs, ys, zs), 
    kdims=['x'], 
    vdims=['y', 'z'],
    hover_fields=['x', 'y', dim('y') / dim('x')],
    hover_aliases={"dim('y')/dim('x')": '比值 (y/x)'}
)
fields4 = scatter4._get_hover_fields()
print('字段:', [scatter4._resolve_hover_field_name(f) for f in fields4])
data4 = scatter4._get_hover_data()
print('数据 keys:', list(data4.keys()))
for k, v in data4.items():
    print(f'  {k}: {v[:3]}...')
tooltips4 = scatter4._get_hover_tooltips_spec()
print('tooltips:', tooltips4)

print()
print('=== 测试 9: hover_formatters ===')
scatter5 = hv.Scatter(
    (xs, ys, zs), 
    kdims=['x'], 
    vdims=['y', 'z'],
    hover_fields=['x', 'y'],
    hover_formatters={'x': '{:.2f}', 'y': lambda v: f'{v:.0f}'}
)
val_x = 3.14159
val_y = 25.0
print(f'格式化 x={val_x}:', scatter5._format_hover_value('x', val_x))
print(f'格式化 y={val_y}:', scatter5._format_hover_value('y', val_y))

print()
print('=== 测试 10: Bokeh 后端集成 ===')
try:
    import holoviews as hv
    hv.extension('bokeh')
    from holoviews.plotting.bokeh.element import ElementPlot
    
    scatter_bokeh = hv.Scatter(
        (xs, ys, zs), 
        kdims=['x'], 
        vdims=['y', 'z'],
        hover_fields=['x', 'y', 'z'],
        hover_aliases={'x': 'X', 'y': 'Y Squared', 'z': 'Z Multiplied'},
        hover_formatters={'x': '{:.1f}'}
    )
    
    print('Bokeh 后端可用')
    print('元素 hover_fields:', scatter_bokeh.hover_fields)
except Exception as e:
    print(f'Bokeh 测试异常: {e}')

print()
print('=== 测试 11: Plotly 后端集成 ===')
try:
    hv.extension('plotly')
    from holoviews.plotting.plotly.element import ElementPlot as PlotlyElementPlot
    
    scatter_plotly = hv.Scatter(
        (xs, ys, zs), 
        kdims=['x'], 
        vdims=['y', 'z'],
        hover_fields=['x', 'y'],
        hover_aliases={'x': 'X Axis', 'y': 'Y Axis'},
    )
    
    print('Plotly 后端可用')
    print('元素 hover_aliases:', scatter_plotly.hover_aliases)
except Exception as e:
    print(f'Plotly 测试异常: {e}')

print()
print('=== 测试 12: Matplotlib 后端集成 ===')
try:
    hv.extension('matplotlib')
    from holoviews.plotting.mpl.element import ElementPlot as MplElementPlot
    
    scatter_mpl = hv.Scatter(
        (xs, ys, zs), 
        kdims=['x'], 
        vdims=['y', 'z'],
        hover_fields=['x', 'y'],
    )
    
    print('Matplotlib 后端可用')
    print('元素 hover_fields:', scatter_mpl.hover_fields)
except Exception as e:
    print(f'Matplotlib 测试异常: {e}')

print()
print('所有测试完成!')
