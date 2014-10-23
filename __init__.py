'''
Copyright (C) 2014 CG Cookie
http://cgcookie.com
hello@cgcookie.com

Created by Jonathan Denning, Jonathan Williamson, and Patrick Moore

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

bl_info = {
    "name":        "Polystrips Retopology Tool",
    "description": "A tool to retopologize complex forms with drawn strips of polygons.",
    "author":      "Jonathan Denning, Jonathan Williamson, Patrick Moore",
    "version":     (1, 0, 0),
    "blender":     (2, 7, 1),
    "location":    "View 3D > Tool Shelf",
    "warning":     "Beta",  # used for warning icon and text in addons panel
    "wiki_url":    "http://cgcookiemarkets.com/blender/all-products/polystrips-retopology-tool-v1-0-0/?view=docs",
    "tracker_url": "https://github.com/CGCookie/retopology-polystrips/issues",
    "category":    "3D View"
    }

# Add the current __file__ path to the search path
import sys, os

import math
import copy
import random
import time
from math import sqrt

import bpy, bmesh, blf, bgl
from bpy.props import EnumProperty, StringProperty, BoolProperty, IntProperty, FloatVectorProperty, FloatProperty
from bpy.types import Operator, AddonPreferences
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_vector_3d, region_2d_to_location_3d
from mathutils import Vector, Matrix, Quaternion
from mathutils.geometry import intersect_line_plane, intersect_point_line

from .lib import common_utilities
from .lib.common_utilities import get_object_length_scale, dprint, profiler, frange
from .lib.common_classes import SketchBrush

from .lib import common_drawing

from . import polystrips
from .polystrips import *
from . import polystrips_utilities
from .polystrips_draw import *


# Used to store keymaps for addon
polystrips_keymaps = []

#used to store undo snapshots
polystrips_undo_cache = []



def showErrorMessage(message, wrap=80):
    lines = []
    if wrap > 0:
        while len(message) > wrap:
            i = message.rfind(' ',0,wrap)
            if i == -1:
                lines += [message[:wrap]]
                message = message[wrap:]
            else:
                lines += [message[:i]]
                message = message[i+1:]
    if message:
        lines += [message]
    def draw(self,context):
        for line in lines:
            self.layout.label(line)
    bpy.context.window_manager.popup_menu(draw, title="Error Message", icon="ERROR")
    return


class PolystripsToolsAddonPreferences(AddonPreferences):
    bl_idname = __name__
    
    def update_theme(self, context):
        print('theme updated to ' + str(theme))
        
    
    debug = IntProperty(
            name="Debug Level",
            default=1,
            min = 0,
            max = 4,
            )
    
    theme = EnumProperty(
        items=[
            ('blue', 'Blue', 'Blue color scheme'),
            ('green', 'Green', 'Green color scheme'),
            ('orange', 'Orange', 'Orange color scheme'),
            ],
        name='theme',
        default='blue'
        )

    theme_colors = {
        'blue': (0, 0, 255, 255) 
    }

    
    show_segment_count = BoolProperty(
        name='Show Selected Segment Count',
        description='Show segment count on selection',
        default=True
        )
    
    quad_prev_radius = IntProperty(
        name="Pixel Brush Radius",
        description = "Pixel brush size",
        default=15,
        )
    
    undo_depth = IntProperty(
        name="Undo Depth",
        description = "Max number of undo steps",
        default=15,
        )
    
    def draw(self, context):
        layout = self.layout
        
        row = layout.row(align=True)
        row.prop(self, "theme", "Theme")
        
        row = layout.row(align=True)
        row.prop(self, "show_segment_count")
        
        row = layout.row(align=True)
        row.prop(self, "debug")



class CGCOOKIE_OT_retopo_polystrips_panel(bpy.types.Panel):
    '''Retopologize Forms with polygon strips'''
    bl_category = "Retopology"
    bl_label = "Polystrips"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    
    @classmethod
    def poll(cls, context):
        mode = bpy.context.mode
        obj = context.active_object
        return (obj and obj.type == 'MESH' and mode in ('OBJECT', 'EDIT_MESH'))
    
    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)

        if 'EDIT' in context.mode and len(context.selected_objects) != 2:
            col.label(text='No 2nd Object!')
        col.operator("cgcookie.polystrips", icon="IPO_BEZIER")



class CGCOOKIE_OT_polystrips(bpy.types.Operator):
    bl_idname = "cgcookie.polystrips"
    bl_label  = "Polystrips"
    
    @classmethod
    def poll(cls,context):
        if context.mode not in {'EDIT_MESH','OBJECT'}:
            return False
        
        if context.active_object:
            if context.mode == 'EDIT_MESH':
                if len(context.selected_objects) > 1:
                    return True
                else:
                    return False
            else:
                return context.object.type == 'MESH'
        else:
            return False
    
    def draw_callback(self, context):
        return self.ui.draw_callback(context)
    
    def modal(self, context, event):
        ret = self.ui.modal(context, event)
        if 'FINISHED' in ret or 'CANCELLED' in ret:
            self.ui.cleanup(context)
            common_utilities.callback_cleanup(self, context)
        return ret
    
    def invoke(self, context, event):
        self.ui = PolystripsUI(context, event)
        
        # switch to modal
        self._handle = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback, (context, ), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}



def register():
    bpy.utils.register_class(CGCOOKIE_OT_polystrips)
    bpy.utils.register_class(CGCOOKIE_OT_retopo_polystrips_panel)
    bpy.utils.register_class(PolystripsToolsAddonPreferences)
    

def unregister():
    bpy.utils.unregister_class(PolystripsToolsAddonPreferences)
    bpy.utils.unregister_class(CGCOOKIE_OT_retopo_polystrips_panel)
    bpy.utils.unregister_class(CGCOOKIE_OT_polystrips)



class PolystripsUI:
    def __init__(self, context, event):
        settings = common_utilities.get_settings()
        
        self.mode = 'main'
        
        self.mode_pos      = (0,0)
        self.cur_pos       = (0,0)
        self.mode_radius   = 0
        self.action_center = (0,0)
        self.action_radius = 0
        self.is_navigating = False
        self.sketch_curpos = (0,0)
        self.sketch_pressure = 1
        self.sketch = []
        
        self.post_update = True
        
        self.footer = ''
        self.footer_last = ''
        
        self.last_matrix = None
        
        self._timer = context.window_manager.event_timer_add(0.1, context.window)
        
        self.stroke_smoothing = 0.5          # 0: no smoothing. 1: no change
        
        if context.mode == 'OBJECT':

            self.obj_orig = context.object
            # duplicate selected objected to temporary object but with modifiers applied
            self.me = self.obj_orig.to_mesh(scene=context.scene, apply_modifiers=True, settings='PREVIEW')
            self.me.update()
            self.obj = bpy.data.objects.new('PolystripsTmp', self.me)
            bpy.context.scene.objects.link(self.obj)
            self.obj.hide = True
            self.obj.matrix_world = self.obj_orig.matrix_world
            self.me.update()
            
            #HACK
            bpy.ops.object.mode_set(mode = 'EDIT')
            bpy.ops.object.mode_set(mode = 'OBJECT')
            
            self.bme = bmesh.new()
            self.bme.from_mesh(self.me)
            
            self.to_obj = None
            self.to_bme = None
            self.snap_eds = []
            self.snap_eds_vis = []
            self.hover_ed = None
            
        if context.mode == 'EDIT_MESH':
            self.obj_orig = [ob for ob in context.selected_objects if ob != context.object][0]
            self.me = self.obj_orig.to_mesh(scene=context.scene, apply_modifiers=True, settings='PREVIEW')
            self.me.update()
            self.bme = bmesh.new()
            self.bme.from_mesh(self.me)
            
            self.obj = bpy.data.objects.new('PolystripsTmp', self.me)
            bpy.context.scene.objects.link(self.obj)
            self.obj.hide = True
            self.obj.matrix_world = self.obj_orig.matrix_world
            self.me.update()
            
            bpy.ops.object.mode_set(mode = 'OBJECT')
            bpy.ops.object.mode_set(mode = 'EDIT')
            
            self.to_obj = context.object
            self.to_bme = bmesh.from_edit_mesh(context.object.data)
            self.snap_eds = [ed for ed in self.to_bme.edges if not ed.is_manifold]
            region,r3d = context.region,context.space_data.region_3d
            mx = self.to_obj.matrix_world
            rv3d = context.space_data.region_3d
            self.snap_eds_vis = [False not in common_utilities.ray_cast_visible([mx * ed.verts[0].co, mx * ed.verts[1].co], self.obj, rv3d) for ed in self.snap_eds]
            self.hover_ed = None
            
        self.scale = self.obj.scale[0]    
        self.length_scale = get_object_length_scale(self.obj)    
        #world stroke radius
        self.stroke_radius = 0.01 * self.length_scale
        self.stroke_radius_pressure = 0.01 * self.length_scale
        #screen_stroke_radius
        self.screen_stroke_radius = 20 #TODO, hood to settings
        
        self.sketch_brush = SketchBrush(context, 
                                        settings, 
                                        event.mouse_region_x, event.mouse_region_y, 
                                        15, #settings.quad_prev_radius, 
                                        self.obj)
        
        self.act_gedge  = None                          # active gedge
        self.sel_gedges = set()
        self.sel_gvert  = None                          # selected gvert
        self.act_gvert  = None                          # active gvert (operated upon)
        
        self.polystrips = PolyStrips(context, self.obj)
        
        polystrips_undo_cache = []  #clear the cache in case any is left over
        if self.obj.grease_pencil:
            self.create_polystrips_from_greasepencil()
        elif 'BezierCurve' in bpy.data.objects:
            self.create_polystrips_from_bezier(bpy.data.objects['BezierCurve'])
        
        context.area.header_text_set('PolyStrips')
    
    ###############################
    def create_undo_snapshot(self, action):
        '''
        unsure about all the _timers get deep copied
        and if act_gedges and verts get copied as references
        or also duplicated, making them no longer valid.
        '''
        settings = common_utilities.get_settings()
        repeated_actions = {'count','zip count'}
        
        if action in repeated_actions and len(polystrips_undo_cache):
            if action == polystrips_undo_cache[-1][1]:
                print('repeatable...dont take snapshot')
                return
        
        p_data = copy.deepcopy(self.polystrips)
        
        if self.act_gedge:
            act_gedge = self.polystrips.gedges.index(self.act_gedge)
        else:
            act_gedge = None
            
        if self.sel_gvert:
            sel_gvert = self.polystrips.gverts.index(self.sel_gvert)
        else:
            sel_gvert = None
            
        if self.act_gvert:
            act_gvert = self.polystrips.gverts.index(self.sel_gvert)
        else:
            act_gvert = None
            
        polystrips_undo_cache.append(([p_data, sel_gvert, act_gedge, act_gvert], action))
            
        if len(polystrips_undo_cache) > settings.undo_depth:
            polystrips_undo_cache.pop(0)
            
            
    def undo_action(self):
        '''
        '''
        if len(polystrips_undo_cache) > 0:
            data, action = polystrips_undo_cache.pop()
            
            self.polystrips = data[0]
            
            if data[1]:
                self.sel_gvert = self.polystrips.gverts[data[1]]
            else:
                self.sel_gvert = None
                
            if data[2]:
                self.act_gedge = self.polystrips.gedges[data[2]]
            else:
                self.act_gedge = None
                
            if data[3]:
                self.act_gvert = self.polystrips.gverts[data[3]]
            else:
                self.act_gvert = None
                

    def cleanup(self, context):
        '''
        remove temporary object
        '''
        dprint('cleaning up!')
        
        tmpobj = self.obj #not always, sometimes if duplicate remains...will be .001
        meobj  = tmpobj.data
        
        # delete object
        context.scene.objects.unlink(tmpobj)
        tmpobj.user_clear()
        if tmpobj.name in bpy.data.objects:
            bpy.data.objects.remove(tmpobj)
        
        bpy.context.scene.update()
        bpy.data.meshes.remove(meobj)
        
    
    ################################
    # draw functions
    
    def draw_callback(self, context):
        settings = common_utilities.get_settings()
        region,r3d = context.region,context.space_data.region_3d
        
        new_matrix = [v for l in r3d.view_matrix for v in l]
        if self.post_update or self.last_matrix != new_matrix:
            for gv in self.polystrips.gverts:
                gv.update_visibility(r3d)
            for ge in self.polystrips.gedges:
                ge.update_visibility(r3d)
            if self.act_gedge:
                for gv in [self.act_gedge.gvert1, self.act_gedge.gvert2]:
                    gv.update_visibility(r3d)
            if self.sel_gvert:
                for gv in self.sel_gvert.get_inner_gverts():
                    gv.update_visibility(r3d)
            
            if len(self.snap_eds):
                mx = self.obj.matrix_world
                self.snap_eds_vis = [False not in common_utilities.ray_cast_visible([mx * ed.verts[0].co, mx * ed.verts[1].co], self.obj, r3d) for ed in self.snap_eds]
            
            self.post_update = False
            self.last_matrix = new_matrix
            
            
        if settings.debug < 3:
            self.draw_callback_themed(context)
        else:
            self.draw_callback_debug(context)
    
        
    def draw_gedge_direction(self, context, gedge, color):
        p0,p1,p2,p3 = gedge.gvert0.snap_pos,  gedge.gvert1.snap_pos,  gedge.gvert2.snap_pos,  gedge.gvert3.snap_pos
        n0,n1,n2,n3 = gedge.gvert0.snap_norm, gedge.gvert1.snap_norm, gedge.gvert2.snap_norm, gedge.gvert3.snap_norm
        pm = cubic_bezier_blend_t(p0,p1,p2,p3,0.5)
        px = cubic_bezier_derivative(p0,p1,p2,p3,0.5).normalized()
        pn = (n0+n3).normalized()
        py = pn.cross(px).normalized()
        rs = (gedge.gvert0.radius+gedge.gvert3.radius) * 0.35
        rl = rs * 0.75
        p3d = [pm-px*rs,pm+px*rs,pm+px*(rs-rl)+py*rl,pm+px*rs,pm+px*(rs-rl)-py*rl]
        common_drawing.draw_polyline_from_3dpoints(context, p3d, color, 5, "GL_LINE_SMOOTH")
    
    def draw_callback_themed(self, context):
        settings = common_utilities.get_settings()
        region,r3d = context.region,context.space_data.region_3d
        
        # theme_number = int(settings.theme)
        

        color_inactive  = (0,0,0)
        color_selection = PolystripsToolsAddonPreferences.theme_colors[settings.theme]
        color_active    = PolystripsToolsAddonPreferences.theme_colors[settings.theme]     # not used at the moment
        
        for i_gp,gpatch in enumerate(self.polystrips.gpatches):
            l0 = len(gpatch.ge0.cache_igverts)
            l1 = len(gpatch.ge1.cache_igverts)
            for i0 in range(1,l0,2):
                r = i0 / (l0-1)
                c = (1,1,1,0.5) # (r,0,1,0.5)
                pts = [p for _i0,_i1,p in gpatch.pts if _i0==i0]
                common_drawing.draw_polyline_from_3dpoints(context, pts, c, 1, "GL_LINE_STIPPLE")
            for i1 in range(1,l1,2):
                g = i1 / (l1-1)
                c = (1,1,1,0.5) # (0,g,1,0.5)
                pts = [p for _i0,_i1,p in gpatch.pts if _i1==i1]
                common_drawing.draw_polyline_from_3dpoints(context, pts, c, 1, "GL_LINE_STIPPLE")
            common_drawing.draw_3d_points(context, [p for _,_,p in gpatch.pts], (1,1,1,0.5), 3)
            
            # draw edge directions
            if settings.debug > 2:
                self.draw_gedge_direction(context, gpatch.ge0, (0.8,0.4,0.4,1.0))
                self.draw_gedge_direction(context, gpatch.ge1, (0.4,0.8,0.4,1.0))
                self.draw_gedge_direction(context, gpatch.ge2, (0.4,0.4,0.8,1.0))
                self.draw_gedge_direction(context, gpatch.ge3, (0.4,0.4,0.4,1.0))
        
        for i_ge,gedge in enumerate(self.polystrips.gedges):
            if gedge == self.act_gedge:
                color_border = (color_selection[0]/255.0, color_selection[1]/255.0, color_selection[2]/255.0, 1.00)
                color_fill   = (color_selection[0]/255.0, color_selection[1]/255.0, color_selection[2]/255.0, 0.20)
            elif gedge in self.sel_gedges:
                color_border = (color_active[0]/255.0, color_active[1]/255.0, color_active[2]/255.0, 1.00)
                color_fill   = (color_active[0]/255.0, color_active[1]/255.0, color_active[2]/255.0, 0.20)
            else:
                color_border = (color_inactive[0]/255.0, color_inactive[1]/255.0, color_inactive[2]/255.0, 1.00)
                color_fill   = (0.5, 0.5, 0.5, 0.2)
            
            for c0,c1,c2,c3 in gedge.iter_segments(only_visible=True):
                common_drawing.draw_quads_from_3dpoints(context, [c0,c1,c2,c3], color_fill)
                common_drawing.draw_polyline_from_3dpoints(context, [c0,c1,c2,c3,c0], color_border, 2, "GL_LINE_SMOOTH")
            
            if settings.debug >= 2:
                # draw bezier
                p0,p1,p2,p3 = gedge.gvert0.snap_pos, gedge.gvert1.snap_pos, gedge.gvert2.snap_pos, gedge.gvert3.snap_pos
                p3d = [cubic_bezier_blend_t(p0,p1,p2,p3,t/16.0) for t in range(17)]
                common_drawing.draw_polyline_from_3dpoints(context, p3d, (1,1,1,0.5),1, "GL_LINE_SMOOTH")
        
        for i_gv,gv in enumerate(self.polystrips.gverts):
            if not gv.is_visible(): continue
            p0,p1,p2,p3 = gv.get_corners()
            
            if gv.is_unconnected(): continue
            
            is_selected = False
            is_selected |= gv == self.sel_gvert
            is_selected |= self.act_gedge!=None and (self.act_gedge.gvert0 == gv or self.act_gedge.gvert1 == gv)
            is_selected |= self.act_gedge!=None and (self.act_gedge.gvert2 == gv or self.act_gedge.gvert3 == gv)
            if is_selected:
                color_border = (color_selection[0]/255.0, color_selection[1]/255.0, color_selection[2]/255.0, 1.00)
                color_fill   = (color_selection[0]/255.0, color_selection[1]/255.0, color_selection[2]/255.0, 0.20)
            else:
                color_border = (color_inactive[0]/255.0, color_inactive[1]/255.0, color_inactive[2]/255.0, 1.00)
                color_fill   = (0.5, 0.5, 0.5, 0.2)
            
            p3d = [p0,p1,p2,p3,p0]
            common_drawing.draw_quads_from_3dpoints(context, [p0,p1,p2,p3], color_fill)
            common_drawing.draw_polyline_from_3dpoints(context, p3d, color_border, 2, "GL_LINE_SMOOTH")
        
        p3d = [gvert.position for gvert in self.polystrips.gverts if not gvert.is_unconnected() and gvert.is_visible()]
        color = (color_inactive[0]/255.0, color_inactive[1]/255.0, color_inactive[2]/255.0, 1.00)
        common_drawing.draw_3d_points(context, p3d, color, 4)
        
        if self.sel_gvert:
            color = (color_selection[0]/255.0, color_selection[1]/255.0, color_selection[2]/255.0, 1.00)
            gv = self.sel_gvert
            p0 = gv.position
            if gv.is_inner():
                p1 = gv.gedge_inner.get_outer_gvert_at(gv).position
                common_drawing.draw_3d_points(context, [p0], color, 8)
                common_drawing.draw_polyline_from_3dpoints(context, [p0,p1], color, 2, "GL_LINE_SMOOTH")
            else:
                p3d = [ge.get_inner_gvert_at(gv).position for ge in gv.get_gedges_notnone() if not ge.is_zippered()]
                common_drawing.draw_3d_points(context, [p0] + p3d, color, 8)
                for p1 in p3d:
                    common_drawing.draw_polyline_from_3dpoints(context, [p0,p1], color, 2, "GL_LINE_SMOOTH")
        
        if self.act_gedge:
            color = (color_selection[0]/255.0, color_selection[1]/255.0, color_selection[2]/255.0, 1.00)
            ge = self.act_gedge
            if self.act_gedge.is_zippered():
                p3d = [ge.gvert0.position, ge.gvert3.position]
                common_drawing.draw_3d_points(context, p3d, color, 8)
            else:
                p3d = [gv.position for gv in ge.gverts()]
                common_drawing.draw_3d_points(context, p3d, color, 8)
                common_drawing.draw_polyline_from_3dpoints(context, [p3d[0], p3d[1]], color, 2, "GL_LINE_SMOOTH")
                common_drawing.draw_polyline_from_3dpoints(context, [p3d[2], p3d[3]], color, 2, "GL_LINE_SMOOTH")
            
            if settings.show_segment_count:
                draw_gedge_info(self.act_gedge, context)
        
        if self.act_gvert:
            color = (color_active[0]/255.0, color_active[1]/255.0, color_active[2]/255.0, 1.00)
            gv = self.act_gvert
            p0 = gv.position
            common_drawing.draw_3d_points(context, [p0], color, 8)
        
        if self.mode == 'sketch':
            # draw smoothing line (end of sketch to current mouse position)
            common_drawing.draw_polyline_from_points(context, [self.sketch_curpos, self.sketch[-1][0]], (0.5,0.5,0.2,0.8), 1, "GL_LINE_SMOOTH")
            
            # draw sketching stroke
            common_drawing.draw_polyline_from_points(context, [co[0] for co in self.sketch], (1,1,.5,.8), 2, "GL_LINE_SMOOTH")
            
            # report pressure reading
            info = str(round(self.sketch_pressure,3))
            txt_width, txt_height = blf.dimensions(0, info)
            d = self.sketch_brush.pxl_rad
            blf.position(0, self.sketch_curpos[0] - txt_width/2, self.sketch_curpos[1] + d + txt_height, 0)
            blf.draw(0, info)
        
        if self.mode in {'scale tool','rotate tool'}:
            # draw a scale/rotate line from tool origin to current mouse position
            common_drawing.draw_polyline_from_points(context, [self.action_center, self.mode_pos], (0,0,0,0.5), 1, "GL_LINE_STIPPLE")
        
        bgl.glLineWidth(1)
        
        if self.mode == 'brush scale tool':
            # scaling brush size
            self.sketch_brush.draw(context, color=(1,1,1,.5), linewidth=1, color_size=(1,1,1,1))
        elif self.mode not in {'grab tool','scale tool','rotate tool'} and not self.is_navigating:
            # draw the brush oriented to surface
            ray,hit = common_utilities.ray_cast_region2d(region, r3d, self.cur_pos, self.obj, settings)
            hit_p3d,hit_norm,hit_idx = hit
            if hit_idx != -1: # and not self.hover_ed:
                mx = self.obj.matrix_world
                mxnorm = mx.transposed().inverted().to_3x3()
                hit_p3d = mx * hit_p3d
                hit_norm = mxnorm * hit_norm
                common_drawing.draw_circle(context, hit_p3d, hit_norm.normalized(), self.stroke_radius_pressure, (1,1,1,.5))
            if self.mode == 'sketch':
                ray,hit = common_utilities.ray_cast_region2d(region, r3d, self.sketch[0][0], self.obj, settings)
                hit_p3d,hit_norm,hit_idx = hit
                if hit_idx != -1:
                    mx = self.obj.matrix_world
                    mxnorm = mx.transposed().inverted().to_3x3()
                    hit_p3d = mx * hit_p3d
                    hit_norm = mxnorm * hit_norm
                    common_drawing.draw_circle(context, hit_p3d, hit_norm.normalized(), self.stroke_radius_pressure, (1,1,1,.5))
        
        if self.hover_ed and False:
            color = (color_selection[0]/255.0, color_selection[1]/255.0, color_selection[2]/255.0, 1.00)
            common_drawing.draw_bmedge(context, self.hover_ed, self.to_obj.matrix_world, 2, color)
    
            
    def draw_callback_debug(self, context):
        settings = common_utilities.get_settings()
        region = context.region
        r3d = context.space_data.region_3d
        
        draw_original_strokes   = False
        draw_gedge_directions   = True
        draw_gvert_orientations = False
        draw_unconnected_gverts = False
        draw_gvert_unsnapped    = False
        draw_gedge_bezier       = False
        draw_gedge_index        = False
        draw_gedge_igverts      = False
        
        cols = [(1,.5,.5,.8),(.5,1,.5,.8),(.5,.5,1,.8),(1,1,.5,.8)]
        
        color_selected          = (.5,1,.5,.8)
        
        color_gedge             = (1,.5,.5,.8)
        color_gedge_nocuts      = (.5,.2,.2,.8)
        color_gedge_zipped      = (.5,.7,.7,.8)
        
        color_gvert_unconnected = (.2,.2,.2,.8)
        color_gvert_endpoint    = (.2,.2,.5,.8)
        color_gvert_endtoend    = (.5,.5,1,.8)
        color_gvert_ljunction   = (1,.5,1,.8)
        color_gvert_tjunction   = (1,1,.5,.8)
        color_gvert_cross       = (1,1,1,.8)
        color_gvert_midpoints   = (.7,1,.7,.8)
        
        t = time.time()
        tf = t - int(t)
        tb = tf*2 if tf < 0.5 else 2-(tf*2)
        tb1 = 1-tb
        sel_fn = lambda c: tuple(cv*tb+cs*tb1 for cv,cs in zip(c,color_selected))
        
        if draw_original_strokes:
            for stroke in self.strokes_original:
                #p3d = [pt for pt,pr in stroke]
                #common_drawing.draw_polyline_from_3dpoints(context, p3d, (.7,.7,.7,.8), 3, "GL_LINE_SMOOTH")
                common_drawing.draw_circle(context, stroke[0][0], Vector((0,0,1)),0.003,(.2,.2,.2,.8))
                common_drawing.draw_circle(context, stroke[-1][0], Vector((0,1,0)),0.003,(.5,.5,.5,.8))
        
        
        for i_ge,gedge in enumerate(self.polystrips.gedges):
            if draw_gedge_directions:
                p0,p1,p2,p3 = gedge.gvert0.snap_pos, gedge.gvert1.snap_pos, gedge.gvert2.snap_pos, gedge.gvert3.snap_pos
                n0,n1,n2,n3 = gedge.gvert0.snap_norm, gedge.gvert1.snap_norm, gedge.gvert2.snap_norm, gedge.gvert3.snap_norm
                pm = cubic_bezier_blend_t(p0,p1,p2,p3,0.5)
                px = cubic_bezier_derivative(p0,p1,p2,p3,0.5).normalized()
                pn = (n0+n3).normalized()
                py = pn.cross(px).normalized()
                rs = (gedge.gvert0.radius+gedge.gvert3.radius) * 0.35
                rl = rs * 0.75
                p3d = [pm-px*rs,pm+px*rs,pm+px*(rs-rl)+py*rl,pm+px*rs,pm+px*(rs-rl)-py*rl]
                common_drawing.draw_polyline_from_3dpoints(context, p3d, (0.8,0.8,0.8,0.8),1, "GL_LINE_SMOOTH")
            
            if draw_gedge_bezier:
                p0,p1,p2,p3 = gedge.gvert0.snap_pos, gedge.gvert1.snap_pos, gedge.gvert2.snap_pos, gedge.gvert3.snap_pos
                p3d = [cubic_bezier_blend_t(p0,p1,p2,p3,t/16.0) for t in range(17)]
                common_drawing.draw_polyline_from_3dpoints(context, p3d, (0.5,0.5,0.5,0.8),1, "GL_LINE_SMOOTH")
            
            col = color_gedge if len(gedge.cache_igverts) else color_gedge_nocuts
            if gedge.zip_to_gedge: col = color_gedge_zipped
            if gedge == self.act_gedge: col = sel_fn(col)
            w = 2 if len(gedge.cache_igverts) else 5
            for c0,c1,c2,c3 in gedge.iter_segments(only_visible=True):
                common_drawing.draw_polyline_from_3dpoints(context, [c0,c1,c2,c3,c0], col, w, "GL_LINE_SMOOTH")
            
            if draw_gedge_index:
                draw_gedge_text(gedge, context, str(i_ge))
            
            if draw_gedge_igverts:
                rm = (gedge.gvert0.radius + gedge.gvert3.radius)*0.1
                for igv in gedge.cache_igverts:
                    common_drawing.common_drawing.draw_circle(context, igv.position, igv.normal, rm, (1,1,1,.3))
        
        for i_gv,gv in enumerate(self.polystrips.gverts):
            if not gv.is_visible(): continue
            p0,p1,p2,p3 = gv.get_corners()
            
            if not draw_unconnected_gverts and gv.is_unconnected() and gv != self.sel_gvert: continue
            
            col = color_gvert_unconnected
            if gv.is_endpoint(): col = color_gvert_endpoint
            elif gv.is_endtoend(): col = color_gvert_endtoend
            elif gv.is_ljunction(): col = color_gvert_ljunction
            elif gv.is_tjunction(): col = color_gvert_tjunction
            elif gv.is_cross(): col = color_gvert_cross
            
            if gv == self.sel_gvert: col = sel_fn(col)
            
            p3d = [p0,p1,p2,p3,p0]
            common_drawing.draw_polyline_from_3dpoints(context, p3d, col, 2, "GL_LINE_SMOOTH")
            
            if draw_gvert_orientations:
                p,x,y = gv.snap_pos,gv.snap_tanx,gv.snap_tany
                common_drawing.draw_polyline_from_3dpoints(context, [p,p+x*0.005], (1,0,0,1), 1, "GL_LINE_SMOOTH")
                common_drawing.draw_polyline_from_3dpoints(context, [p,p+y*0.005], (0,1,0,1), 1, "GL_LINE_SMOOTH")
        
        if draw_gvert_unsnapped:
            for gv in self.polystrips.gverts:
                p,x,y,n = gv.position,gv.snap_tanx,gv.snap_tany,gv.snap_norm
                common_drawing.draw_polyline_from_3dpoints(context, [p,p+x*0.01], (1,0,0,1), 1, "GL_LINE_SMOOTH")
                common_drawing.draw_polyline_from_3dpoints(context, [p,p+y*0.01], (0,1,0,1), 1, "GL_LINE_SMOOTH")
                common_drawing.draw_polyline_from_3dpoints(context, [p,p+n*0.01], (0,0,1,1), 1, "GL_LINE_SMOOTH")
        
        if self.act_gedge:
            if not self.act_gedge.zip_to_gedge:
                col = color_gvert_midpoints
                for gv in self.act_gedge.get_inner_gverts():
                    if not gv.is_visible(): continue
                    p0,p1,p2,p3 = gv.get_corners()
                    p3d = [p0,p1,p2,p3,p0]
                    common_drawing.draw_polyline_from_3dpoints(context, p3d, col, 2, "GL_LINE_SMOOTH")
            draw_gedge_info(self.act_gedge, context)
        
        if self.sel_gvert:
            col = color_gvert_midpoints
            for ge in self.sel_gvert.get_gedges_notnone():
                if ge.zip_to_gedge: continue
                gv = ge.get_inner_gvert_at(self.sel_gvert)
                if not gv.is_visible(): continue
                p0,p1,p2,p3 = gv.get_corners()
                p3d = [p0,p1,p2,p3,p0]
                common_drawing.draw_polyline_from_3dpoints(context, p3d, col, 2, "GL_LINE_SMOOTH")
        
        if self.mode == 'sketch':
            common_drawing.draw_polyline_from_points(context, [self.sketch_curpos, self.sketch[-1][0]], (0.5,0.5,0.2,0.8), 1, "GL_LINE_SMOOTH")
            common_drawing.draw_polyline_from_points(context, [co[0] for co in self.sketch], (1,1,.5,.8), 2, "GL_LINE_SMOOTH")
            
            info = str(round(self.sketch_pressure,3))
            ''' draw text '''
            txt_width, txt_height = blf.dimensions(0, info)
            d = self.sketch_brush.pxl_rad
            blf.position(0, self.sketch_curpos[0] - txt_width/2, self.sketch_curpos[1] + d + txt_height, 0)
            blf.draw(0, info)
        
            
        if self.mode in {'scale tool','rotate tool'}:
            common_drawing.draw_polyline_from_points(context, [self.action_center, self.mode_pos], (0,0,0,0.5), 1, "GL_LINE_STIPPLE")
        
        bgl.glLineWidth(1)
        
        if self.mode not in {'grab tool','scale tool','rotate tool','brush scale tool'}:
            ray,hit = common_utilities.ray_cast_region2d(region, r3d, self.cur_pos, self.obj, settings)
            hit_p3d,hit_norm,hit_idx = hit
            if hit_idx != -1:
                mx = self.obj.matrix_world
                hit_p3d = mx * hit_p3d
                common_drawing.draw_circle(context, hit_p3d, hit_norm.normalized(), self.stroke_radius_pressure, (1,1,1,.5))
        
        if not self.hover_ed:
            self.sketch_brush.draw(context)
        else:
            common_drawing.draw_bmedge(context, self.hover_ed, self.to_obj.matrix_world, 2, color_selected)
    
    
    ############################
    # function to convert polystrips => mesh
    
    def create_mesh(self, context):
        verts,quads = self.polystrips.create_mesh()
        
        if self.to_bme and self.to_obj:  #EDIT MDOE on Existing Mesh
            bm = self.to_bme
            mx = self.to_obj.matrix_world
            imx = mx.inverted()
            
            mx2 = self.obj.matrix_world
            imx2 = mx2.inverted()
            
        else:
            bm = bmesh.new()
            mx2 = Matrix.Identity(4)
            imx = Matrix.Identity(4)
            
            nm_polystrips = self.obj.name + "_polystrips"
        
            dest_me  = bpy.data.meshes.new(nm_polystrips)
            dest_obj = bpy.data.objects.new(nm_polystrips, dest_me)
        
            dest_obj.matrix_world = self.obj.matrix_world
            dest_obj.update_tag()
            dest_obj.show_all_edges = True
            dest_obj.show_wire      = True
            dest_obj.show_x_ray     = True
            
            context.scene.objects.link(dest_obj)
            dest_obj.select = True
            context.scene.objects.active = dest_obj
            
        
        bmverts = [bm.verts.new(imx * mx2 * v) for v in verts]
        bm.verts.index_update()
        for q in quads: bm.faces.new([bmverts[i] for i in q])
        
        bm.faces.index_update()
        
        if self.to_bme and self.to_obj:
            bmesh.update_edit_mesh(self.to_obj.data, tessface=False, destructive=True)
            bm.free()
        else: 
            bm.to_mesh(dest_me)
            bm.free()
    
    ###########################
    # fill function
    
    def fill(self, eventd):
        if len(self.sel_gedges) != 2:
            showErrorMessage('Must have exactly 2 selected edges')
            return
        
        # check that we have a hole
        # TODO: handle multiple edges on one side
        
        lgedges = list(self.sel_gedges)
        lgedge,rgedge = lgedges
        tlgvert = lgedge.gvert0
        blgvert = lgedge.gvert3
        
        trgvert,brgvert = None,None
        tgedge,bgedge = None,None
        for gv in [rgedge.gvert0,rgedge.gvert3]:
            for ge in gv.get_gedges_notnone():
                if ge.gvert0 == tlgvert:
                    trgvert = ge.gvert3
                    tgedge = ge
                if ge.gvert0 == blgvert:
                    brgvert = ge.gvert3
                    bgedge = ge
                if ge.gvert3 == tlgvert:
                    trgvert = ge.gvert0
                    tgedge = ge
                if ge.gvert3 == blgvert:
                    brgvert = ge.gvert0
                    bgedge = ge
        
        # handle cases where selected gedges have no or only one connecting gedge
        if not trgvert and not brgvert:
            # create two gedges
            dl = (blgvert.position - tlgvert.position).normalized()
            d0 = (rgedge.gvert0.position - tlgvert.position).normalized()
            d3 = (rgedge.gvert3.position - tlgvert.position).normalized()
            if dl.dot(d0) > dl.dot(d3):
                trgvert = rgedge.gvert3
                brgvert = rgedge.gvert0
            else:
                trgvert = rgedge.gvert0
                brgvert = rgedge.gvert3
            tgedge = self.polystrips.insert_gedge_between_gverts(tlgvert, trgvert)
            bgedge = self.polystrips.insert_gedge_between_gverts(blgvert, brgvert)
        elif not trgvert and brgvert:
            if brgvert == rgedge.gvert0:
                trgvert = rgedge.gvert3
            else:
                trgvert = rgedge.gvert0
            tgedge = self.polystrips.insert_gedge_between_gverts(tlgvert, trgvert)
        elif not brgvert and trgvert:
            if trgvert == rgedge.gvert0:
                brgvert = rgedge.gvert3
            else:
                brgvert = rgedge.gvert0
            bgedge = self.polystrips.insert_gedge_between_gverts(blgvert, brgvert)
        
        if not all(gv.is_ljunction for gv in [trgvert,tlgvert,blgvert,brgvert]):
            showErrorMessage('All corners must be L-Junctions')
            return
        
        self.polystrips.create_gpatch(lgedge, bgedge, rgedge, tgedge)
        
    
    ###########################
    # hover functions
    
    def hover_geom(self,eventd):
        if not len(self.snap_eds): return 
        context = eventd['context']
        region,r3d = context.region,context.space_data.region_3d
        new_matrix = [v for l in r3d.view_matrix for v in l]
        x, y = eventd['mouse']
        mouse_loc = Vector((x,y))
        mx = self.to_obj.matrix_world
        
        if self.post_update or self.last_matrix != new_matrix:
            #update all the visibility stuff
            self.snap_eds_vis = [False not in common_utilities.ray_cast_visible([mx * ed.verts[0].co, mx * ed.verts[1].co], self.obj, r3d) for ed in self.snap_eds]
           
        #sticky highlight...check the hovered edge first
        if self.hover_ed:
            a = location_3d_to_region_2d(region, r3d, mx * self.hover_ed.verts[0].co)
            b = location_3d_to_region_2d(region, r3d, mx * self.hover_ed.verts[1].co)
            
            if a and b:
                intersect = intersect_point_line(mouse_loc, a, b)
                dist = (intersect[0] - mouse_loc).length_squared
                bound = intersect[1]
                if (dist < 100) and (bound < 1) and (bound > 0):
                    return
    
        self.hover_ed = None
        for i,ed in enumerate(self.snap_eds):
            if self.snap_eds_vis[i]:
                a = location_3d_to_region_2d(region, r3d, mx * ed.verts[0].co)
                b = location_3d_to_region_2d(region, r3d, mx * ed.verts[1].co)
                if a and b:
                    intersect = intersect_point_line(mouse_loc, a, b)
    
                    dist = (intersect[0] - mouse_loc).length_squared
                    bound = intersect[1]
                    if (dist < 100) and (bound < 1) and (bound > 0):
                        self.hover_ed = ed
                        break
                    
                        
    ###########################
    # tool functions
    
    def ready_tool(self, eventd, tool_fn):
        rgn   = eventd['context'].region
        r3d   = eventd['context'].space_data.region_3d
        mx,my = eventd['mouse']
        if self.sel_gvert:
            loc   = self.sel_gvert.position
            cx,cy = location_3d_to_region_2d(rgn, r3d, loc)
        elif self.act_gedge:
            loc   = (self.act_gedge.gvert0.position + self.act_gedge.gvert3.position) / 2.0
            cx,cy = location_3d_to_region_2d(rgn, r3d, loc)
        else:
            cx,cy = mx-100,my
        rad   = math.sqrt((mx-cx)**2 + (my-cy)**2)
        
        self.action_center = (cx,cy)
        self.mode_start    = (mx,my)
        self.action_radius = rad
        self.mode_radius   = rad
        
        self.prev_pos      = (mx,my)
        
        # spc = bpy.data.window_managers['WinMan'].windows[0].screen.areas[4].spaces[0]
        # r3d = spc.region_3d
        vrot = r3d.view_rotation
        self.tool_x = (vrot * Vector((1,0,0))).normalized()
        self.tool_y = (vrot * Vector((0,1,0))).normalized()
        
        self.tool_rot = 0.0
        
        self.tool_fn = tool_fn
        self.tool_fn('init', eventd)
    
    def scale_tool_gvert(self, command, eventd):
        if command == 'init':
            self.footer = 'Scaling GVerts'
            sgv = self.sel_gvert
            lgv = [ge.gvert1 if ge.gvert0==sgv else ge.gvert2 for ge in sgv.get_gedges() if ge]
            self.tool_data = [(gv,Vector(gv.position)) for gv in lgv]
        elif command == 'commit':
            pass
        elif command == 'undo':
            for gv,p in self.tool_data:
                gv.position = p
                gv.update()
            self.sel_gvert.update()
            self.sel_gvert.update_visibility(eventd['r3d'], update_gedges=True)
        else:
            m = command
            sgv = self.sel_gvert
            p = sgv.position
            for ge in sgv.get_gedges():
                if not ge: continue
                gv = ge.gvert1 if ge.gvert0 == self.sel_gvert else ge.gvert2
                gv.position = p + (gv.position-p) * m
                gv.update()
            sgv.update()
            self.sel_gvert.update_visibility(eventd['r3d'], update_gedges=True)
    
    def scale_tool_gvert_radius(self, command, eventd):
        if command == 'init':
            self.footer = 'Scaling GVert radius'
            self.tool_data = self.sel_gvert.radius
        elif command == 'commit':
            pass
        elif command == 'undo':
            self.sel_gvert.radius = self.tool_data
            self.sel_gvert.update()
            self.sel_gvert.update_visibility(eventd['r3d'], update_gedges=True)
        else:
            m = command
            self.sel_gvert.radius *= m
            self.sel_gvert.update()
            self.sel_gvert.update_visibility(eventd['r3d'], update_gedges=True)
    
    def scale_tool_stroke_radius(self, command, eventd):
        if command == 'init':
            self.footer = 'Scaling Stroke radius'
            self.tool_data = self.stroke_radius
        elif command == 'commit':
            pass
        elif command == 'undo':
            self.stroke_radius = self.tool_data
        else:
            m = command
            self.stroke_radius *= m
    
    def grab_tool_gvert_list(self, command, eventd, lgv):
        '''
        translates list of gverts
        note: translation is relative to first gvert
        '''
        def l3dr2d(p): return location_3d_to_region_2d(eventd['region'], eventd['r3d'], p)
        
        if command == 'init':
            self.footer = 'Translating GVert position(s)'
            s2d = l3dr2d(lgv[0].position)
            self.tool_data = [(gv, Vector(gv.position), l3dr2d(gv.position)-s2d) for gv in lgv]
        elif command == 'commit':
            pass
        elif command == 'undo':
            for gv,p,_ in self.tool_data: gv.position = p
            for gv,_,_ in self.tool_data:
                gv.update()
                gv.update_visibility(eventd['r3d'], update_gedges=True)
        else:
            factor_slow,factor_fast = 0.2,1.0
            dv = Vector(command) * (factor_slow if eventd['shift'] else factor_fast)
            s2d = l3dr2d(self.tool_data[0][0].position)
            lgv2d = [s2d+relp+dv for _,_,relp in self.tool_data]
            pts = common_utilities.ray_cast_path(eventd['context'], self.obj, lgv2d)
            if len(pts) != len(lgv2d): return ''
            for d,p2d in zip(self.tool_data, pts):
                d[0].position = p2d
            for gv,_,_ in self.tool_data:
                gv.update()
                gv.update_visibility(eventd['r3d'], update_gedges=True)
        
    def grab_tool_gvert(self, command, eventd):
        '''
        translates selected gvert
        '''
        if command == 'init':
            lgv = [self.sel_gvert]
        else:
            lgv = None
        self.grab_tool_gvert_list(command, eventd, lgv)
    
    def grab_tool_gvert_neighbors(self, command, eventd):
        '''
        translates selected gvert and its neighbors
        note: translation is relative to selected gvert
        '''
        if command == 'init':
            sgv = self.sel_gvert
            lgv = [sgv] + [ge.get_inner_gvert_at(sgv) for ge in sgv.get_gedges_notnone()]
        else:
            lgv = None
        self.grab_tool_gvert_list(command, eventd, lgv)
    
    def grab_tool_gedge(self, command, eventd):
        if command == 'init':
            sge = self.act_gedge
            lgv = [sge.gvert0, sge.gvert3]
            lgv += [ge.get_inner_gvert_at(gv) for gv in lgv for ge in gv.get_gedges_notnone()]
        else:
            lgv = None
        self.grab_tool_gvert_list(command, eventd, lgv)
    
    def rotate_tool_gvert_neighbors(self, command, eventd):
        if command == 'init':
            self.footer = 'Rotating GVerts'
            self.tool_data = [(gv,Vector(gv.position)) for gv in self.sel_gvert.get_inner_gverts()]
        elif command == 'commit':
            pass
        elif command == 'undo':
            for gv,p in self.tool_data:
                gv.position = p
                gv.update()
        else:
            ang = command
            q = Quaternion(self.sel_gvert.snap_norm, ang)
            p = self.sel_gvert.position
            for gv,up in self.tool_data:
                gv.position = p+q*(up-p)
                gv.update()
    
    def scale_brush_pixel_radius(self,command, eventd):
        if command == 'init':
            self.footer = 'Scale Brush Pixel Size'
            self.tool_data = self.stroke_radius
            x,y = eventd['mouse']
            self.sketch_brush.brush_pix_size_init(eventd['context'], x, y)
        elif command == 'commit':
            self.sketch_brush.brush_pix_size_confirm(eventd['context'])
            if self.sketch_brush.world_width:
                self.stroke_radius = self.sketch_brush.world_width
        elif command == 'undo':
            self.sketch_brush.brush_pix_size_cancel(eventd['context'])
            self.stroke_radius = self.tool_data
        else:
            x,y = command
            self.sketch_brush.brush_pix_size_interact(x, y, precise = eventd['shift'])
    
    
    ##############################
    # modal state functions
    
    def modal_nav(self, eventd):
        events_numpad = {
            'NUMPAD_1',       'NUMPAD_2',       'NUMPAD_3',
            'NUMPAD_4',       'NUMPAD_5',       'NUMPAD_6',
            'NUMPAD_7',       'NUMPAD_8',       'NUMPAD_9',
            'CTRL+NUMPAD_1',  'CTRL+NUMPAD_2',  'CTRL+NUMPAD_3',
            'CTRL+NUMPAD_4',  'CTRL+NUMPAD_5',  'CTRL+NUMPAD_6',
            'CTRL+NUMPAD_7',  'CTRL+NUMPAD_8',  'CTRL+NUMPAD_9',
            'SHIFT+NUMPAD_1', 'SHIFT+NUMPAD_2', 'SHIFT+NUMPAD_3',
            'SHIFT+NUMPAD_4', 'SHIFT+NUMPAD_5', 'SHIFT+NUMPAD_6',
            'SHIFT+NUMPAD_7', 'SHIFT+NUMPAD_8', 'SHIFT+NUMPAD_9',
            'NUMPAD_PLUS', 'NUMPAD_MINUS', # CTRL+NUMPAD_PLUS and CTRL+NUMPAD_MINUS are used elsewhere
            'NUMPAD_PERIOD',
        }
        
        handle_nav = False
        handle_nav |= eventd['type'] == 'MIDDLEMOUSE'
        handle_nav |= eventd['type'] == 'MOUSEMOVE' and self.is_navigating
        handle_nav |= eventd['type'].startswith('NDOF_')
        handle_nav |= eventd['type'].startswith('TRACKPAD')
        handle_nav |= eventd['ftype'] in events_numpad
        handle_nav |= eventd['ftype'] in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}
        
        if handle_nav:
            self.post_update = True
            self.is_navigating = True
            
            # x,y = eventd['mouse']
            # self.sketch_brush.update_mouse_move_hover(eventd['context'], x,y)
            # self.sketch_brush.make_circles()
            # self.sketch_brush.get_brush_world_size(eventd['context'])
            
            # if self.sketch_brush.world_width:
            #     self.stroke_radius = self.sketch_brush.world_width
            #     self.stroke_radius_pressure = self.sketch_brush.world_width
                
            return 'nav' if eventd['value']=='PRESS' else 'main'
        
        self.is_navigating = False
        return ''
    
    def modal_main(self, eventd):
        self.footer = 'LMB: draw, RMB: select, G: grab, R: rotate, S: scale, F: brush size, K: knife, M: merge, X: delete, CTRL+D: dissolve, CTRL+Wheel Up/Down: adjust segments, CTRL+C: change selected junction type'
        
        #############################################
        # general navigation
        
        nmode = self.modal_nav(eventd)
        if nmode:
            return nmode
        
        ########################################
        # accept / cancel
        
        if eventd['press'] in {'RET', 'NUMPAD_ENTER'}:
            self.create_mesh(eventd['context'])
            eventd['context'].area.header_text_set()
            return 'finish'
        
        if eventd['press'] in {'ESC'}:
            eventd['context'].area.header_text_set()
            return 'cancel'
        
        
        #####################################
        # general
        
        if eventd['type'] == 'MOUSEMOVE':  #mouse movement/hovering
            #update brush and brush size
            x,y = eventd['mouse']
            self.sketch_brush.update_mouse_move_hover(eventd['context'], x,y)
            self.sketch_brush.make_circles()
            self.sketch_brush.get_brush_world_size(eventd['context'])
            
            if self.sketch_brush.world_width:
                self.stroke_radius = self.sketch_brush.world_width
                self.stroke_radius_pressure = self.sketch_brush.world_width
            
            self.hover_geom(eventd)
        
        
        if eventd['press'] == 'CTRL+Z':
            self.undo_action()
            return ''
        
        if eventd['press'] == 'F':
            self.ready_tool(eventd, self.scale_brush_pixel_radius)
            return 'brush scale tool'
        
        if eventd['press'] == 'Q':                                                  # profiler printout
            profiler.printout()
            return ''
        
        if eventd['press'] == 'P':                                                  # grease pencil => strokes
            # TODO: only convert gpencil strokes that are visible and prevent duplicate conversion
            for gpl in self.obj.grease_pencil.layers: gpl.hide = True
            for stroke in self.strokes_original:
                self.polystrips.insert_gedge_from_stroke(stroke, True)
            self.polystrips.remove_unconnected_gverts()
            self.polystrips.update_visibility(eventd['r3d'])
            return ''
        
        
        if eventd['press'] in {'LEFTMOUSE','SHIFT+LEFTMOUSE'}:
            self.create_undo_snapshot('sketch')
            # start sketching
            self.footer = 'Sketching'
            x,y = eventd['mouse']
            p   = eventd['pressure']
            r   = eventd['mradius']
            
            self.sketch_curpos = (x,y)
            
            if eventd['shift'] and self.sel_gvert:
                # continue sketching from selected gvert position
                gvx,gvy = location_3d_to_region_2d(eventd['region'], eventd['r3d'], self.sel_gvert.position)
                self.sketch = [((gvx,gvy),self.sel_gvert.radius), ((x,y),r)]
            else:
                self.sketch = [((x,y),r)]
            
            self.sel_gvert = None
            self.act_gedge = None
            self.sel_gedges = set()
            return 'sketch'
        
        if eventd['press'] in {'RIGHTMOUSE','SHIFT+RIGHTMOUSE'}:                            # picking
            x,y = eventd['mouse']
            pts = common_utilities.ray_cast_path(eventd['context'], self.obj, [(x,y)])
            if not pts:
                self.sel_gvert,self.act_gedge,self.act_gvert = None,None,None
                self.sel_gedges.clear()
                return ''
            pt = pts[0]
            
            if self.sel_gvert or self.act_gedge:
                # check if user is picking an inner control point
                if self.act_gedge and not self.act_gedge.zip_to_gedge:
                    lcpts = [self.act_gedge.gvert1,self.act_gedge.gvert2]
                elif self.sel_gvert:
                    sgv = self.sel_gvert
                    lge = self.sel_gvert.get_gedges()
                    lcpts = [ge.get_inner_gvert_at(sgv) for ge in lge if ge and not ge.zip_to_gedge] + [sgv]
                else:
                    lcpts = []
                
                for cpt in lcpts:
                    if not cpt.is_picked(pt): continue
                    self.sel_gvert = cpt
                    self.act_gedge = None
                    self.sel_gedges.clear()
                    return ''
            
            for gv in self.polystrips.gverts:
                if gv.is_unconnected(): continue
                if not gv.is_picked(pt): continue
                self.sel_gvert = gv
                self.act_gedge = None
                self.sel_gedges.clear()
                return ''
            
            for ge in self.polystrips.gedges:
                if not ge.is_picked(pt): continue
                self.sel_gvert = None
                self.act_gedge = ge
                if not eventd['shift']:
                    self.sel_gedges.clear()
                self.sel_gedges.add(ge)
                return ''
            
            self.act_gedge,self.sel_gvert = None,None
            self.sel_gedges.clear()
            return ''
        
        if eventd['press'] == 'CTRL+LEFTMOUSE':                                     # delete/dissolve
            x,y = eventd['mouse']
            pts = common_utilities.ray_cast_path(eventd['context'], self.obj, [(x,y)])
            if not pts:
                self.sel_gvert,self.act_gedge,self.act_gvert = None,None,None
                return ''
            pt = pts[0]
            
            for gv in self.polystrips.gverts:
                if not gv.is_picked(pt): continue
                if not (gv.is_endpoint() or gv.is_endtoend() or gv.is_ljunction()): continue
                
                if gv.is_endpoint():
                    self.polystrips.disconnect_gvert(gv)
                else:
                    self.polystrips.dissolve_gvert(gv)
                
                self.polystrips.remove_unconnected_gverts()
                self.polystrips.update_visibility(eventd['r3d'])
                
                self.sel_gvert = None
                self.act_gedge = None
                self.sel_gedges.clear()
                return ''
            
            for ge in self.polystrips.gedges:
                if not ge.is_picked(pt): continue
                
                self.polystrips.disconnect_gedge(ge)
                self.polystrips.remove_unconnected_gverts()
                
                self.sel_gvert = None
                self.act_gedge = None
                self.sel_gedges.clear()
                return ''
            
            self.act_gedge,self.sel_gvert = None,None
            return ''
        
        if eventd['press'] == 'CTRL+U':
            self.create_undo_snapshot('update')
            for gv in self.polystrips.gverts:
                gv.update_gedges()
        
        
        ###################################
        # selected gedge commands
        
        if self.act_gedge:
            if eventd['press'] == 'X':
                self.create_undo_snapshot('delete')
                self.polystrips.disconnect_gedge(self.act_gedge)
                self.act_gedge = None
                self.sel_gedges.clear()
                self.polystrips.remove_unconnected_gverts()
                return ''
            
            if eventd['press'] == 'K' and not self.act_gedge.is_zippered() and not self.act_gedge.has_zippered():
                self.create_undo_snapshot('knife')
                x,y = eventd['mouse']
                pts = common_utilities.ray_cast_path(eventd['context'], self.obj, [(x,y)])
                if not pts:
                    return ''
                pt = pts[0]
                t,_    = self.act_gedge.get_closest_point(pt)
                _,_,gv = self.polystrips.split_gedge_at_t(self.act_gedge, t)
                self.act_gedge = None
                self.sel_gedges.clear()
                self.sel_gvert = gv
            
            if eventd['press'] == 'U':
                self.create_undo_snapshot('update')
                self.act_gedge.gvert0.update_gedges()
                self.act_gedge.gvert3.update_gedges()
                return ''
            
            if eventd['press']in {'OSKEY+WHEELUPMOUSE', 'CTRL+NUMPAD_PLUS'}:
                self.create_undo_snapshot('count')
                self.act_gedge.set_count(self.act_gedge.n_quads + 1)
                return ''
            
            if eventd['press'] in {'OSKEY+WHEELDOWNMOUSE', 'CTRL+NUMPAD_MINUS'}:
    
                if self.act_gedge.n_quads > 3:
                    self.create_undo_snapshot('count')
                    self.act_gedge.set_count(self.act_gedge.n_quads - 1)
                return ''
            
            if eventd['press'] == 'Z':
                
                if self.act_gedge.zip_to_gedge:
                    self.create_undo_snapshot('unzip')
                    self.act_gedge.unzip()
                    return ''
                
                lge = self.act_gedge.gvert0.get_gedges_notnone() + self.act_gedge.gvert3.get_gedges_notnone()
                if any(ge.is_zippered() for ge in lge):
                    # prevent zippering a gedge with gvert that has a zippered gedge already
                    # TODO: allow this??
                    return ''
                
                x,y = eventd['mouse']
                pts = common_utilities.ray_cast_path(eventd['context'], self.obj, [(x,y)])
                if not pts:
                    return ''
                pt = pts[0]
                for ge in self.polystrips.gedges:
                    if ge == self.act_gedge: continue
                    if not ge.is_picked(pt): continue
                    self.create_undo_snapshot('zip')
                    self.act_gedge.zip_to(ge)
                    return ''
                return ''
            
            if eventd['press'] == 'G':
                if not self.act_gedge.is_zippered():
                    self.create_undo_snapshot('grab')
                    self.ready_tool(eventd, self.grab_tool_gedge)
                    return 'grab tool'
                return ''
            
            if eventd['press'] == 'A':
                self.sel_gvert = self.act_gedge.gvert0
                self.act_gedge = None
                self.sel_gedges.clear()
                return ''
            if eventd['press'] == 'B':
                self.sel_gvert = self.act_gedge.gvert3
                self.act_gedge = None
                self.sel_gedges.clear()
                return ''
            
            if eventd['press'] == 'CTRL+R' and not self.act_gedge.is_zippered():
                self.create_undo_snapshot('rib')
                self.act_gedge = self.polystrips.rip_gedge(self.act_gedge)
                self.sel_gedges = [self.act_gedge]
                self.ready_tool(eventd, self.grab_tool_gedge)
                return 'grab tool'
        
        #if len(self.sel_gedges) > 2:
        if eventd['press'] == 'SHIFT+F':
            self.create_undo_snapshot('simplefill')
            self.fill(eventd)
            
            return ''
        
        ###################################
        # selected gvert commands
        
        if self.sel_gvert:
            
            if eventd['press'] == 'K':
                if not self.sel_gvert.is_endpoint():
                    print('Selected GVert must be endpoint (exactly one GEdge)')
                    return ''
                x,y = eventd['mouse']
                pts = common_utilities.ray_cast_path(eventd['context'], self.obj, [(x,y)])
                if not pts:
                    return ''
                pt = pts[0]
                for ge in self.polystrips.gedges:
                    if not ge.is_picked(pt): continue
                    self.create_undo_snapshot('split')
                    t,d = ge.get_closest_point(pt)
                    self.polystrips.split_gedge_at_t(ge, t, connect_gvert=self.sel_gvert)
                    return ''
                return ''
            
            if eventd['press'] == 'X':
                if self.sel_gvert.is_inner():
                    return ''
                self.create_undo_snapshot('delete')
                self.polystrips.disconnect_gvert(self.sel_gvert)
                self.sel_gvert = None
                self.polystrips.remove_unconnected_gverts()
                return ''
            
            if eventd['press'] == 'CTRL+D':
                self.create_undo_snapshot('dissolve')
                self.polystrips.dissolve_gvert(self.sel_gvert)
                self.sel_gvert = None
                self.polystrips.remove_unconnected_gverts()
                self.polystrips.update_visibility(eventd['r3d'])
                return ''
            
            if eventd['press'] == 'S':
                self.create_undo_snapshot('scale')
                self.ready_tool(eventd, self.scale_tool_gvert_radius)
                return 'scale tool'
            
            
            if eventd['press'] == 'CTRL+G':
                self.create_undo_snapshot('grab')
                self.ready_tool(eventd, self.grab_tool_gvert)
                return 'grab tool'
            
            if eventd['press'] == 'G':
                self.create_undo_snapshot('grab')
                self.ready_tool(eventd, self.grab_tool_gvert_neighbors)
                return 'grab tool'
            
            
            if eventd['press'] == 'CTRL+C':
                self.create_undo_snapshot('toggle')
                self.sel_gvert.toggle_corner()
                self.sel_gvert.update_visibility(eventd['r3d'], update_gedges=True)
                return ''
            
            
            if eventd['press'] == 'CTRL+S':
                self.create_undo_snapshot('scale')
                self.ready_tool(eventd, self.scale_tool_gvert)
                return 'scale tool'
            
            if eventd['press'] == 'C':
                self.create_undo_snapshot('smooth')
                self.sel_gvert.smooth()
                self.sel_gvert.update_visibility(eventd['r3d'], update_gedges=True)
                return ''
            
            if eventd['press'] == 'R':
                self.create_undo_snapshot('rotate')
                self.ready_tool(eventd, self.rotate_tool_gvert_neighbors)
                return 'rotate tool'
            
            if eventd['press'] == 'U':
                self.sel_gvert.update_gedges()
                return ''
            
            if eventd['press'] == 'CTRL+R':
                # self.polystrips.rip_gvert(self.sel_gvert)
                # self.sel_gvert = None
                # return ''
                x,y = eventd['mouse']
                pts = common_utilities.ray_cast_path(eventd['context'], self.obj, [(x,y)])
                if not pts:
                    return ''
                pt = pts[0]
                for ge in self.sel_gvert.get_gedges_notnone():
                    if not ge.is_picked(pt): continue
                    self.create_undo_snapshot('rip')
                    self.sel_gvert = self.polystrips.rip_gedge(ge, at_gvert=self.sel_gvert)
                    self.ready_tool(eventd, self.grab_tool_gvert_neighbors)
                    return 'grab tool'
                return ''
            
            if eventd['press'] == 'M':
                if self.sel_gvert.is_inner(): return ''
                x,y = eventd['mouse']
                pts = common_utilities.ray_cast_path(eventd['context'], self.obj, [(x,y)])
                if not pts:
                    return ''
                pt = pts[0]
                sel_ge = set(self.sel_gvert.get_gedges_notnone())
                for gv in self.polystrips.gverts:
                    if gv.is_inner() or not gv.is_picked(pt) or gv == self.sel_gvert: continue
                    if len(self.sel_gvert.get_gedges_notnone()) + len(gv.get_gedges_notnone()) > 4:
                        dprint('Too many connected GEdges for merge!')
                        continue
                    if any(ge in sel_ge for ge in gv.get_gedges_notnone()):
                        dprint('Cannot merge GVerts that share a GEdge')
                        continue
                    self.create_undo_snapshot('merge')
                    self.polystrips.merge_gverts(self.sel_gvert, gv)
                    self.sel_gvert = gv
                    return ''
                return ''
                
            
            if self.sel_gvert.zip_over_gedge:
                gvthis = self.sel_gvert
                gvthat = self.sel_gvert.get_zip_pair()
                
                if eventd['press'] == 'CTRL+NUMPAD_PLUS':
                    self.create_undo_snapshot('zip count')
                    max_t = 1 if gvthis.zip_t>gvthat.zip_t else gvthat.zip_t-0.05
                    gvthis.zip_t = min(gvthis.zip_t+0.05, max_t)
                    gvthis.zip_over_gedge.update()
                    dprint('+ %f %f' % (min(gvthis.zip_t, gvthat.zip_t),max(gvthis.zip_t, gvthat.zip_t)), l=4)
                    return ''
                
                if eventd['press'] == 'CTRL+NUMPAD_MINUS':
                    self.create_undo_snapshot('zip count')
                    min_t = 0 if gvthis.zip_t<gvthat.zip_t else gvthat.zip_t+0.05
                    gvthis.zip_t = max(gvthis.zip_t-0.05, min_t)
                    gvthis.zip_over_gedge.update()
                    dprint('- %f %f' % (min(gvthis.zip_t, gvthat.zip_t),max(gvthis.zip_t, gvthat.zip_t)), l=4)
                    return ''
                
        return ''
    
    def modal_sketching(self, eventd):
        #my_str = eventd['type'] + ' ' + str(round(eventd['pressure'],2)) + ' ' + str(round(self.stroke_radius_pressure,2))
        #print(my_str)
        if eventd['type'] == 'MOUSEMOVE':
            x,y = eventd['mouse']
            p = eventd['pressure']
            r = eventd['mradius']
            
            stroke_point = self.sketch[-1]
            
            (lx, ly) = stroke_point[0]
            lr = stroke_point[1]
            self.sketch_curpos = (x,y)
            self.sketch_pressure = p

            ss0,ss1 = self.stroke_smoothing,1-self.stroke_smoothing
            #smooth radii
            self.stroke_radius_pressure = lr*ss0 + r*ss1
            
            self.sketch += [((lx*ss0+x*ss1, ly*ss0+y*ss1), self.stroke_radius_pressure)]
            
            
            return ''
        
        if eventd['release'] in {'LEFTMOUSE','SHIFT+LEFTMOUSE'}:
            #correct for 0 pressure on release
            if self.sketch[-1][1] == 0:
                self.sketch[-1] = self.sketch[-2]
                
            p3d = common_utilities.ray_cast_stroke(eventd['context'], self.obj, self.sketch) if len(self.sketch) > 1 else []
            if len(p3d) <= 1: return 'main'
            
            # tessellate stroke (if needed) so we have good stroke sampling
            #TODO, tesselate pressure/radius values?
            #length_tess = self.length_scale / 700
            #p3d = [(p0+(p1-p0).normalized()*x) for p0,p1 in zip(p3d[:-1],p3d[1:]) for x in frange(0,(p0-p1).length,length_tess)] + [p3d[-1]]
            #stroke = [(p,self.stroke_radius) for i,p in enumerate(p3d)]
            
            stroke = p3d
            self.sketch = []
            dprint('')
            dprint('')
            dprint('inserting stroke')
            self.polystrips.insert_gedge_from_stroke(stroke, False)
            self.polystrips.remove_unconnected_gverts()
            self.polystrips.update_visibility(eventd['r3d'])
            return 'main'
        
        return ''
    
    
    ##############################
    # modal tool functions
    
    def modal_scale_tool(self, eventd):
        cx,cy = self.action_center
        mx,my = eventd['mouse']
        ar = self.action_radius
        pr = self.mode_radius
        cr = math.sqrt((mx-cx)**2 + (my-cy)**2)
        
        if eventd['press'] in {'RET','NUMPAD_ENTER','LEFTMOUSE'}:
            self.tool_fn('commit', eventd)
            return 'main'
        
        if eventd['press'] in {'ESC', 'RIGHTMOUSE'}:
            self.tool_fn('undo', eventd)
            return 'main'
        
        if eventd['type'] == 'MOUSEMOVE':
            self.tool_fn(cr / pr, eventd)
            self.mode_radius = cr
            return ''
        
        return ''
    
    def modal_grab_tool(self, eventd):
        cx,cy = self.action_center
        mx,my = eventd['mouse']
        px,py = self.prev_pos #mode_pos
        sx,sy = self.mode_start
        
        if eventd['press'] in {'RET','NUMPAD_ENTER','LEFTMOUSE','SHIFT+RET','SHIFT+NUMPAD_ENTER','SHIFT+LEFTMOUSE'}:
            self.tool_fn('commit', eventd)
            return 'main'
        
        if eventd['press'] in {'ESC','RIGHTMOUSE'}:
            self.tool_fn('undo', eventd)
            return 'main'
        
        if eventd['type'] == 'MOUSEMOVE':
            self.tool_fn((mx-px,my-py), eventd)
            self.prev_pos = (mx,my)
            return ''
        
        return ''
    
    def modal_rotate_tool(self, eventd):
        cx,cy = self.action_center
        mx,my = eventd['mouse']
        px,py = self.prev_pos #mode_pos
        
        if eventd['press'] in {'RET', 'NUMPAD_ENTER', 'LEFTMOUSE'}:
            self.tool_fn('commit', eventd)
            return 'main'
        
        if eventd['press'] in {'ESC', 'RIGHTMOUSE'}:
            self.tool_fn('undo', eventd)
            return 'main'
        
        if eventd['type'] == 'MOUSEMOVE':
            vp = Vector((px-cx,py-cy,0))
            vm = Vector((mx-cx,my-cy,0))
            ang = vp.angle(vm) * (-1 if vp.cross(vm).z<0 else 1)
            self.tool_rot += ang
            self.tool_fn(self.tool_rot, eventd)
            self.prev_pos = (mx,my)
            return ''
        
        return ''
    
    def modal_scale_brush_pixel_tool(self, eventd):
        '''
        This is the pixel brush radius
        self.tool_fn is expected to be self.
        '''
        mx,my = eventd['mouse']

        if eventd['press'] in {'RET','NUMPAD_ENTER','LEFTMOUSE'}:
            self.tool_fn('commit', eventd)
            return 'main'
        
        if eventd['press'] in {'ESC', 'RIGHTMOUSE'}:
            self.tool_fn('undo', eventd)
            
            return 'main'
        
        if eventd['type'] == 'MOUSEMOVE':
            '''
            '''
            self.tool_fn((mx,my), eventd)
            
            return ''
        
        return ''
    
    
    ###########################
    # main modal function (FSM)
    
    def modal(self, context, event):
        context.area.tag_redraw()
        settings = common_utilities.get_settings()
        
        eventd = self.get_event_details(context, event)
        
        if self.footer_last != self.footer:
            context.area.header_text_set('PolyStrips: %s' % self.footer)
            self.footer_last = self.footer
        
        FSM = {}
        FSM['main']         = self.modal_main
        FSM['nav']          = self.modal_nav
        FSM['sketch']       = self.modal_sketching
        FSM['scale tool']   = self.modal_scale_tool
        FSM['grab tool']    = self.modal_grab_tool
        FSM['rotate tool']  = self.modal_rotate_tool
        FSM['brush scale tool'] = self.modal_scale_brush_pixel_tool
        
        self.cur_pos = eventd['mouse']
        nmode = FSM[self.mode](eventd)
        self.mode_pos = eventd['mouse']
        
        self.is_navigating = (nmode == 'nav')
        if nmode == 'nav': return {'PASS_THROUGH'}
        
        if nmode in {'finish','cancel'}:
            self.kill_timer(context)
            polystrips_undo_cache = []
            return {'FINISHED'} if nmode == 'finish' else {'CANCELLED'}
        
        if nmode: self.mode = nmode
        
        return {'RUNNING_MODAL'}
    
    
    ###########################################################
    # functions to convert beziers and gpencils to polystrips
    
    def create_polystrips_from_bezier(self, ob_bezier):
        data  = ob_bezier.data
        mx    = ob_bezier.matrix_world
        
        def create_gvert(self, mx, co, radius):
            p0  = mx * co
            r0  = radius
            n0  = Vector((0,0,1))
            tx0 = Vector((1,0,0))
            ty0 = Vector((0,1,0))
            return GVert(self.obj,p0,r0,n0,tx0,ty0)
        
        for spline in data.splines:
            pregv = None
            for bp0,bp1 in zip(spline.bezier_points[:-1],spline.bezier_points[1:]):
                gv0 = pregv if pregv else self.create_gvert(mx, bp0.co, 0.2)
                gv1 = self.create_gvert(mx, bp0.handle_right, 0.2)
                gv2 = self.create_gvert(mx, bp1.handle_left, 0.2)
                gv3 = self.create_gvert(mx, bp1.co, 0.2)
                
                ge0 = GEdge(self.obj, gv0, gv1, gv2, gv3)
                ge0.recalc_igverts_approx()
                ge0.snap_igverts_to_object()
                
                if pregv:
                    self.polystrips.gverts += [gv1,gv2,gv3]
                else:
                    self.polystrips.gverts += [gv0,gv1,gv2,gv3]
                self.polystrips.gedges += [ge0]
                pregv = gv3
    
    def create_polystrips_from_greasepencil(self):
        Mx = self.obj.matrix_world
        gp = self.obj.grease_pencil
        gp_layers = gp.layers
        #for gpl in gp_layers: gpl.hide = True
        strokes = [[(p.co,p.pressure) for p in stroke.points] for layer in gp_layers for frame in layer.frames for stroke in frame.strokes]
        self.strokes_original = strokes
        
        #for stroke in strokes:
        #    self.polystrips.insert_gedge_from_stroke(stroke)
    
    
    ##########################
    # general functions
    
    def kill_timer(self, context):
        if not self._timer: return
        context.window_manager.event_timer_remove(self._timer)
        self._timer = None
    
    def get_event_details(self, context, event):
        '''
        Construct an event dict that is *slightly* more convenient than
        stringing together a bunch of logical conditions
        '''
        
        event_ctrl    = 'CTRL+'  if event.ctrl  else ''
        event_shift   = 'SHIFT+' if event.shift else ''
        event_alt     = 'ALT+'   if event.alt   else ''
        event_oskey   = 'OSKEY+' if event.oskey else ''
        event_ftype   = event_ctrl + event_shift + event_alt + event_oskey + event.type
        
        event_pressure = 1 if not hasattr(event, 'pressure') else event.pressure
        
        def pressure_to_radius(r, p, map = 3):
            if   map == 0:  p = max(0.25,p)
            elif map == 1:  p = 0.25 + .75 * p
            elif map == 2:  p = max(0.05,p)
            elif map == 3:  p = .7 * (2.25*p-1)/((2.25*p-1)**2 +1)**.5 + .55
            return r*p
        
        return {
            'context':  context,
            'region':   context.region,
            'r3d':      context.space_data.region_3d,
            
            'ctrl':     event.ctrl,
            'shift':    event.shift,
            'alt':      event.alt,
            'value':    event.value,
            'type':     event.type,
            'ftype':    event_ftype,
            'press':    event_ftype if event.value=='PRESS'   else None,
            'release':  event_ftype if event.value=='RELEASE' else None,
            
            'mouse':    (float(event.mouse_region_x), float(event.mouse_region_y)),
            'pressure': event_pressure,
            'mradius':  pressure_to_radius(self.stroke_radius, event_pressure),
            }



