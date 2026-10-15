"""Rebuild the small geometric Mira mark without external image assets."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent.parent / 'assets'
root.mkdir(exist_ok=True)
image = Image.new('RGBA',(256,256),(0,0,0,0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8,8,248,248),radius=62,fill='#e9e0f8')
draw.line([(69,187),(69,74),(128,144),(187,74),(187,187)],fill='#7854a5',width=22,joint='curve')
image.save(root/'mira.png')
image.save(root/'mira.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
