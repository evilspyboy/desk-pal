"""Position sleep particles beside the head, respecting source crops and mirroring."""
def head_anchor(skeleton, size, crop=None):
    try:
        x,y=skeleton['joints']['head'];w,h=size
        cx,cy,cw,ch=crop or (0,0,w,h)
        point=((x*w-cx)/cw,(y*h-cy)/ch)
        if all(0 <= v <= 1 for v in point):return point
    except (KeyError,TypeError,ValueError,ZeroDivisionError):pass
    return (.25,.2)


def head_radius(skeleton, size, crop=None):
    try:
        radius=float(skeleton['head_radius'][1])*size[1]/(crop[3] if crop else size[1])
        if 0 < radius < .5:return radius
    except (KeyError,TypeError,ValueError,ZeroDivisionError):pass
    return .1


def particle_origin(draw_x, draw_y, width, height, anchor=None, flipped=False, radius=.1):
    x,y=anchor or (.25,.2)
    if flipped:x=1-x
    return draw_x+width*x, draw_y+height*(y-radius)-18
