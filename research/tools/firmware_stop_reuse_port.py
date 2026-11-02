#!/usr/bin/env python3
"""Research-only portable form of the original indexed-node unlink primitive."""
def make_unlink_adapter(read_word,write_word,log):
    def unlink(a):
        root=read_word(a.get('R0'));index=a.get('R1');stride=(12*index)&0xFFFFFFFF
        node=(root+stride)&0xFFFFFFFF;next_node=read_word(node);previous=read_word(node+4)
        if next_node==previous==0:
            # Original272414 writes zero to4 and0. On the host these null-page
            # stores have no container-state effect and are omitted explicitly.
            log.append(dict(index=index,node=node,next=0,previous=0))
        else:
            assert next_node and previous,(hex(node),hex(next_node),hex(previous))
            write_word(next_node+4,previous);write_word(previous,next_node)
        a.set('R1',stride);a.set('R2',next_node);a.set('R3',previous)
        return node
    return unlink
