"""Pack exact glyph pixels from the authoring atlas; no resampling or font substitution."""
from PIL import Image

def pack_font(source, metadata, destination):
    image = Image.open(source).convert('RGBA')
    width, x, y, row_height = 512, 2, 2, 0
    pieces, glyphs = [], []
    for i, _ in enumerate(metadata['chars']):
        cx, cy = (i % 10) * 128, (i // 10) * 88
        cell = image.crop((cx, cy, cx + 128, cy + 88))
        box = cell.getchannel('A').getbbox()
        if box is None:
            glyphs.append([0,0,0,0,0,0]); continue
        l,t,r,b = box
        # Transparent guard pixels preserve linear filtering at fractional positions.
        l,t,r,b = max(0,l-2),max(0,t-2),min(128,r+2),min(88,b+2)
        w,h = r-l,b-t
        if x+w+2 > width: x,y,row_height = 2,y+(row_height+1)//2*2+2,0
        glyphs.append([x/2,y/2,w/2,h/2,l/2-4,t/2-metadata['size']])
        pieces.append((cell.crop((l,t,r,b)),x,y))
        x += (w+1)//2*2+2; row_height=max(row_height,h)
    height=(y+row_height+3)//2*2
    atlas=Image.new('RGBA',(width,height))
    for glyph,x,y in pieces: atlas.paste(glyph,(x,y))
    atlas.save(destination)
    return {**metadata,'glyphs':glyphs}
