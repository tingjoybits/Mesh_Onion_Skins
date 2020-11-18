
# ##### BEGIN GPL LICENSE BLOCK #####
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENCE BLOCK #####

import bpy
import time
import gpu
import bgl
import numpy as np
from bpy.props import *
from bpy.types import Menu, Panel, AddonPreferences
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix

bl_info = {
    'name': "Mesh Onion Skins",
    'author': "TingJoyBits",
    'version': (1, 0, 5),
    'blender': (2, 80, 0),
    'location': "View3D > Animation > Mesh Onion Skins",
    'description': "Mesh Onion Skins for Blender Animations",
    'wiki_url': "https://gumroad.com/l/OqkKG",
    'category': "Animation"}


OS_collection_name = "Mesh Onion Skins"
OS_empty_name = "Mesh_Onion_Skins"
MAT_PREFIX = "onion_skins_mat_"
SUFFIX_before = "before"
SUFFIX_after = "after"
SUFFIX_marker = "marker"
SUFFIX_own = "own"
OS_Selected_Object_Sets = {}
OS_Selected_Object_Collection = {}
SEPARATOR = "{|SEPARATOR|}"
CREATING = False
RENDERING = False
Active_Object = None
GPU_FRAMES = {}
GPU_MARKERS = {}
DRAW_TOGGLE = False
SHADER = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
Draw_Handler = None
Draw_Timer = None


def checkout_parent(obj):
    if not obj:
        return None
    try:
        if obj.parent.name:
            objp = obj.parent
    except AttributeError:
        objp = obj
    if obj.type == 'ARMATURE':
        objp = obj
    return objp


def traverse_tree(t):
    yield t
    for child in t.children:
        yield from traverse_tree(child)


def parent_lookup(coll):
    parent_lookup = {}
    for coll in traverse_tree(coll):
        for c in coll.children.keys():
            try:
                if parent_lookup[c]:
                    parent_lookup[c].append(coll.name)
            except KeyError:
                parent_lookup[c] = [coll.name]
    return parent_lookup


def list_to_str(input_list, seperator):
    # Join all the strings in list
    try:
        final_str = seperator.join(input_list)
    except TypeError:
        final_str = ''
        for items in input_list:
            final_str = final_str + str(items[0]) + ', ' + str(items[1]) + seperator
    return final_str


def childrens_lookup(obj, list_type='obj'):
    objs = []
    for ob in traverse_tree(obj):
        for o in ob.children:
            if o.name != ob.name:
                if list_type == 'obj':
                    objs.append(o)
                if list_type == 'name':
                    objs.append(o.name)
    return objs


def text_lookup(find_string, source_text):
    if source_text.find(find_string) != -1:
        return True
    else:
        return False


def mesh_show_wire(self, context):
    obj = context.active_object
    wm = context.window_manager
    params = wm.onionSkinsParams
    if obj.type == 'MESH':
        if params.mesh_wire is True:
            if obj.show_wire is not True:
                obj.show_wire = True
        if params.mesh_wire is not True:
            if obj.show_wire is True:
                obj.show_wire = False
    children_list = [i.name for i in wm.os_childrens_collection]
    childrens = childrens_lookup(obj, list_type='name') + children_list
    for c in childrens:
        ob = bpy.data.objects[c]
        if ob.type != 'MESH':
            continue
        if params.mesh_wire is True:
            if ob.show_wire is not True:
                ob.show_wire = True
        else:
            if ob.show_wire is True:
                ob.show_wire = False


def mesh_show_inFront(self, context):
    obj = context.active_object
    wm = context.window_manager
    params = wm.onionSkinsParams
    if obj.type == 'MESH':
        if params.mesh_inFront is True:
            if obj.show_in_front is not True:
                obj.show_in_front = True
        if params.mesh_inFront is not True:
            if obj.show_in_front is True:
                obj.show_in_front = False
    children_list = [i.name for i in wm.os_childrens_collection]
    childrens = childrens_lookup(obj, list_type='name') + children_list
    for c in childrens:
        ob = bpy.data.objects[c]
        if ob.type != 'MESH':
            continue
        if params.mesh_inFront is True:
            if ob.show_in_front is not True:
                ob.show_in_front = True
        else:
            if ob.show_in_front is True:
                ob.show_in_front = False


def shading_color_type(self, context):
    sc = bpy.context.scene.onion_skins_scene_props
    params = bpy.context.window_manager.onionSkinsParams
    shading = bpy.context.space_data.shading
    if params.color_type == 'MATERIAL' and shading.color_type != 'MATERIAL':
        shading.color_type = 'MATERIAL'
    if params.color_type == 'TEXTURE' and shading.color_type != 'TEXTURE':
        shading.color_type = 'TEXTURE'
    if params.color_type == 'OBJECT' and shading.color_type != 'OBJECT':
        shading.color_type = 'OBJECT'
    if sc.view_range:
        view_range_frames(context.scene)
    else:
        set_onion_colors('BEFORE')
        set_onion_colors('AFTER')
        set_onion_colors('MARKER')


def set_base_material_colors(skin_prefix):
    mat_color = get_prefix_material_color(skin_prefix)
    m = get_base_material(skin_prefix)
    if not m:
        create_skins_materials()
        m = get_base_material(skin_prefix)
    if m:
        set_material_color(m, mat_color)


def update_color_bf(self, context):
    tree = get_empty_objs_tree()
    if not tree:
        set_base_material_colors('before')
        return None
    set_onion_colors('BEFORE')
    sc = bpy.context.scene.onion_skins_scene_props
    if sc.view_range:
        view_range_frames(context.scene)


def update_color_af(self, context):
    tree = get_empty_objs_tree()
    if not tree:
        set_base_material_colors('after')
        return None
    set_onion_colors('AFTER')
    sc = bpy.context.scene.onion_skins_scene_props
    if sc.view_range:
        view_range_frames(context.scene)


def update_color_m(self, context):
    tree = get_empty_objs_tree(False, 'MARKER')
    if not tree:
        set_base_material_colors('marker')
        return None
    set_onion_colors('MARKER')


def update_colors(self, context):
    sc = bpy.context.scene.onion_skins_scene_props
    set_onion_colors('BEFORE', fade=True)
    set_onion_colors('AFTER', fade=True)
    set_onion_colors('MARKER')
    if sc.fade_to_alpha is False:
        update_fade_alpha(self, context)
    if sc.view_range:
        view_range_frames(context.scene)


def update_color_alpha(self, context):
    sc = bpy.context.scene.onion_skins_scene_props
    if sc.color_alpha:
        sc.mat_color_bf[3] = sc.color_alpha_value
        sc.mat_color_af[3] = sc.color_alpha_value
        sc.mat_color_m[3] = sc.color_alpha_value
    else:
        sc.mat_color_bf[3] = 1.0
        sc.mat_color_af[3] = 1.0
        sc.mat_color_m[3] = 1.0
        if sc.fade_to_alpha:
            sc.fade_to_alpha = False
    set_onion_colors('BEFORE')
    set_onion_colors('AFTER')
    set_onion_colors('MARKER')
    if sc.view_range:
        view_range_frames(context.scene)


def update_fade_alpha(self, context):
    sc = bpy.context.scene.onion_skins_scene_props
    tree = get_empty_objs_tree()
    if not tree:
        return None
    if sc.fade_to_alpha is False:
        for s in tree.children:
            try:
                if sc.onionsk_colors:
                    if s.name.split('_')[0] == 'before':
                        s.data.materials[0] = bpy.data.materials[MAT_PREFIX + SUFFIX_before]
                    if s.name.split('_')[0] == 'after':
                        s.data.materials[0] = bpy.data.materials[MAT_PREFIX + SUFFIX_after]
                else:
                    s.data.materials[0] = bpy.data.materials[
                        MAT_PREFIX + list_to_str(s.name.split('_')[1:-1], '_') + '_' + SUFFIX_own]
            except KeyError:
                pass
    if sc.color_alpha is False and sc.fade_to_alpha is True:
        sc.color_alpha = True
    set_onion_colors('BEFORE')
    set_onion_colors('AFTER')
    if sc.view_range:
        view_range_frames(context.scene)


def update_os_prop_toggle(prop):
    sc = bpy.context.scene.onion_skins_scene_props
    treeM = get_empty_objs_tree(False, 'MARKER')
    treeOS = get_empty_objs_tree(False)
    markers = []
    oskins = []
    if not treeOS and not treeM:
        return None
    if treeM:
        markers = [s for s in treeM.children]
    if treeOS:
        oskins = [s for s in treeOS.children]
    skins = markers + oskins
    for s in skins:
        if prop == 'wire':
            if sc.onionsk_wire:
                s.show_wire = True
            else:
                s.show_wire = False
        if prop == 'in_renders':
            if sc.show_in_render:
                s.hide_render = False
            else:
                s.hide_render = True
        if prop == 'selectable':
            if sc.os_selectable:
                s.hide_select = False
            else:
                s.hide_select = True
    if sc.view_range and prop == 'in_renders':
        view_range_frames(bpy.context.scene)


def update_os_prop_toggle_wire(self, context):
    update_os_prop_toggle('wire')


def update_os_prop_toggle_in_renders(self, context):
    update_os_prop_toggle('in_renders')


def update_os_prop_toggle_selectable(self, context):
    update_os_prop_toggle('selectable')


def update_view_range(self, context):
    sc = bpy.context.scene.onion_skins_scene_props
    if sc.view_range:
        view_range_frames(context.scene)
        return None
    tree = get_empty_objs_tree()
    if not tree:
        return None
    for s in tree.children:
        if sc.show_in_render:
            s.hide_render = True
        if s.name.split('_')[0] == 'before':
            if sc.hide_os_before is False:
                s.hide_viewport = True
            else:
                s.hide_viewport = False
        if s.name.split('_')[0] == 'after':
            if sc.hide_os_after is False:
                s.hide_viewport = True
            else:
                s.hide_viewport = False
    if sc.fade_to_alpha:
        sc.fade_to_alpha = True
    else:
        sc.fade_to_alpha = False


def update_mpath(self, context):
    sc = bpy.context.scene.onion_skins_scene_props
    if sc.onionsk_mpath is False:
        remove_motion_paths()
        return None
    mode = bpy.context.mode
    obj = context.selected_objects[0]
    objp = checkout_parent(obj)
    curframe = context.scene.frame_current
    global CREATING
    CREATING = True
    if sc.onionsk_method == 'FRAME':
        return_count_fs_fe = OS_OT_CreateUpdate_Skins.os_method_frame(
            self, objp, curframe, dont_create=True)
        fs = return_count_fs_fe[0]
        fe = return_count_fs_fe[1]
        context.scene.frame_set(curframe)
        create_update_motion_path(context, mode, obj, fs, fe, [], [])
    if sc.onionsk_method == 'SCENE':
        fs = sc.onionsk_fr_start
        fe = sc.onionsk_fr_end
        skip = sc.onionsk_skip
        # use playback range
        if sc.onionsk_fr_sc:
            fs = bpy.context.scene.frame_start
            fe = bpy.context.scene.frame_end
        if sc.onionsk_action_range:
            all_keys = OS_OT_CreateUpdate_Skins.os_methos_keyframe(
                self, obj, objp, curframe, dont_create=True)
            fs = all_keys[2][0]
            fe = all_keys[2][-1]
        # fix start to end
        if fe < fs:
            swap = fs
            fs = fe
            fe = swap
        context.scene.frame_set(curframe)
        create_update_motion_path(context, mode, obj, fs, fe, [], [])
    if sc.onionsk_method == 'KEYFRAME':
        return_count_kfb_kfa = OS_OT_CreateUpdate_Skins.os_methos_keyframe(
            self, obj, objp, curframe, dont_create=True)
        if not return_count_kfb_kfa:
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode=mode)
            CREATING = False
            return None
        kfbefore = return_count_kfb_kfa[0]
        kfafter = return_count_kfb_kfa[1]
        context.scene.frame_set(curframe)
        create_update_motion_path(context, mode, obj, 0, 0, kfbefore, kfafter)
    bpy.ops.object.mode_set(mode=mode)
    CREATING = False


def update_tmarker(self, context):
    sc = context.scene.onion_skins_scene_props
    if sc.onionsk_tmarker is False:
        remove_time_markers()
        return None
    if sc.os_draw_technic == 'GPU':
        objp = checkout_parent(context.active_object)
        if not GPU_FRAMES.get(objp.name):
            return None
        frame_nums = list(set([int(float(f.split('|@|')[-1]))
                               for f in GPU_FRAMES[objp.name]]))
    else:
        tree = get_empty_objs_tree(False)
        if not tree:
            return None
        frame_nums = [float(s.name.split('_')[-1]) for s in tree.children]
        frame_nums = list(set(frame_nums))
    tmarkers = context.scene.timeline_markers
    for frame in frame_nums:
        tmarkers.new("os", frame=frame)


def update_os_draw_technic(self, context):
    sc = context.scene.onion_skins_scene_props
    if sc.onionsk_tmarker:
        remove_time_markers()
        update_tmarker(self, context)


def get_empty_objs_tree(active_obj=False, skin_type='ONION'):
    if not active_obj:
        try:
            active_obj = bpy.context.active_object
        except AttributeError:
            wm = bpy.context.window_manager
            active_obj = bpy.data.objects[wm.active_os_set.split('|<@>|')[0]]
    objp = checkout_parent(active_obj)
    if not objp:
        return False
    try:
        if skin_type == 'ONION':
            tree = bpy.data.objects["onionsk_"+objp.name]
        elif skin_type == 'MARKER':
            tree = bpy.data.objects["onionsk_M_"+objp.name]
        return tree
    except KeyError:
        return False


def hide_before_frames(self, context):
    sc = bpy.context.scene.onion_skins_scene_props
    tree = get_empty_objs_tree()
    if tree:
        for s in tree.children:
            if s.name.split('_')[0] == 'before':
                if sc.hide_os_before is False:
                    s.hide_viewport = True
                else:
                    s.hide_viewport = False
    if not sc.hide_os_before:
        if sc.hide_os_all:
            hide_all_os_frames(switch=True, value=False)
    check_all_frames_flag()
    if sc.view_range:
        view_range_frames(context.scene)


def hide_after_frames(self, context):
    sc = bpy.context.scene.onion_skins_scene_props
    tree = get_empty_objs_tree()
    if tree:
        for s in tree.children:
            if s.name.split('_')[0] == 'after':
                if sc.hide_os_after is False:
                    s.hide_viewport = True
                else:
                    s.hide_viewport = False
    if not sc.hide_os_after:
        if sc.hide_os_all:
            hide_all_os_frames(switch=True, value=False)
    check_all_frames_flag()
    if sc.view_range:
        view_range_frames(context.scene)


def hide_marker_frames(self, context):
    sc = bpy.context.scene.onion_skins_scene_props
    tree = get_empty_objs_tree(False, 'MARKER')
    if tree:
        for s in tree.children:
            if sc.hide_os_marker is False:
                s.hide_viewport = True
            else:
                s.hide_viewport = False
    if not sc.hide_os_marker:
        if sc.hide_os_all:
            hide_all_os_frames(switch=True, value=False)
    check_all_frames_flag()


switch_os_all_frames_flag = False


def check_all_frames_flag():
    sc = bpy.context.scene.onion_skins_scene_props
    if sc.hide_os_before and sc.hide_os_after and sc.hide_os_marker:
        if not sc.hide_os_all:
            sc.hide_os_all = True


def hide_all_os_frames(switch=False, value=False):
    sc = bpy.context.scene.onion_skins_scene_props
    if switch:
        global switch_os_all_frames_flag
        switch_os_all_frames_flag = True
        if value:
            if not sc.hide_os_all:
                sc.hide_os_all = True
        if not value:
            if sc.hide_os_all:
                sc.hide_os_all = False
        return None
    if sc.hide_os_all:
        if not sc.hide_os_before:
            sc.hide_os_before = True
        if not sc.hide_os_after:
            sc.hide_os_after = True
        if not sc.hide_os_marker:
            sc.hide_os_marker = True
    if not sc.hide_os_all:
        if sc.hide_os_before:
            sc.hide_os_before = False
        if sc.hide_os_after:
            sc.hide_os_after = False
        if sc.hide_os_marker:
            sc.hide_os_marker = False
    if sc.view_range:
        view_range_frames(bpy.context.scene)


def hide_all_frames(self, context):
    global switch_os_all_frames_flag
    if switch_os_all_frames_flag:
        switch_os_all_frames_flag = False
        return None
    hide_all_os_frames()


def actions_check(obj):
    try:
        actions = bpy.data.objects[obj.name].animation_data.action
    except AttributeError:
        actions = False
    try:
        if obj.parent.animation_data.action:
            actions = True
    except AttributeError:
        pass
    return actions


def handler_check(handler, function_name):
    if len(handler) <= 0:
        return False
    for i, h in enumerate(handler):
        func = str(handler[i]).split(' ')[1]
        if func == function_name:
            return True
    return False


def OS_Initialization():
    params = bpy.context.window_manager.onionSkinsParams
    if params.onion_skins_init:
        return None
    prefs = bpy.context.preferences.addons[__name__].preferences
    sc = bpy.context.scene.onion_skins_scene_props
    remove_handlers(bpy.context)
    global GPU_FRAMES
    global GPU_MARKERS
    GPU_FRAMES.clear()
    GPU_MARKERS.clear()

    if not handler_check(bpy.app.handlers.load_post, "m_os_on_file_load"):
        bpy.app.handlers.load_post.append(m_os_on_file_load)
    if not handler_check(bpy.app.handlers.depsgraph_update_post, "m_os_post_dpgraph_update"):
        bpy.app.handlers.depsgraph_update_post.append(m_os_post_dpgraph_update)
    if not handler_check(bpy.app.handlers.save_pre, "m_os_pre_save"):
        bpy.app.handlers.save_pre.append(m_os_pre_save)
    if not handler_check(bpy.app.handlers.frame_change_post, "m_os_post_frames_handler"):
        bpy.app.handlers.frame_change_post.append(m_os_post_frames_handler)
    if not handler_check(bpy.app.handlers.render_pre, "m_os_pre_render_handler"):
        bpy.app.handlers.render_pre.append(m_os_pre_render_handler)
    if not handler_check(bpy.app.handlers.render_post, "m_os_post_render_handler"):
        bpy.app.handlers.render_post.append(m_os_post_render_handler)
    if not handler_check(bpy.app.handlers.render_cancel, "m_os_cancel_render_handler"):
        bpy.app.handlers.render_cancel.append(m_os_cancel_render_handler)

    if prefs.display_progress:
        params.display_progress = True

    shading = bpy.context.space_data.shading
    if shading.color_type != 'MATERIAL' and shading.color_type != 'TEXTURE' and \
            shading.color_type != 'OBJECT':
        params.color_type = 'MATERIAL'
    if shading.color_type == 'MATERIAL':
        params.color_type = 'MATERIAL'
    if shading.color_type == 'TEXTURE':
        params.color_type = 'TEXTURE'
    if shading.color_type == 'OBJECT':
        params.color_type = 'OBJECT'
    try:
        m = bpy.data.materials[MAT_PREFIX + SUFFIX_before]
    except KeyError:
        sc.mat_color_bf = prefs.color_bf
    try:
        m = bpy.data.materials[MAT_PREFIX + SUFFIX_after]
    except KeyError:
        sc.mat_color_af = prefs.color_af
    try:
        m = bpy.data.materials[MAT_PREFIX + SUFFIX_marker]
    except KeyError:
        sc.mat_color_m = prefs.color_m
    load_os_list_settings()
    item_ob = get_active_index_obj(bpy.context)
    if item_ob:
        params.active_obj_index_list_name = item_ob.name

    params.onion_skins_init = True


def check_draw_gpu_toggle(scene):
    global Active_Object
    if Active_Object != bpy.context.active_object:
        sc = scene.onion_skins_scene_props
        global DRAW_TOGGLE
        if sc.draw_gpu_toggle:
            DRAW_TOGGLE = True
        else:
            DRAW_TOGGLE = False
    else:
        return None
    if not bpy.context.active_object:
        return None
    if len(bpy.context.selected_objects) != 1:
        return None
    if bpy.context.selected_objects[0] != bpy.context.active_object:
        return None
    mode = bpy.context.mode
    try:
        if ((bpy.context.selected_objects[0].type == 'MESH') or (
                bpy.context.active_object.type == 'ARMATURE')) and (
                mode == 'OBJECT' or mode == 'POSE'):
            Active_Object = bpy.context.active_object
        else:
            return None
    except (IndexError, AttributeError) as e:
        return None
    if Active_Object.is_onionsk or Active_Object.is_os_marker:
        if sc.onionsk_tmarker:
            sc.onionsk_tmarker = False
            sc.onionsk_tmarker = True
        remove_handlers(bpy.context)
        if DRAW_TOGGLE and sc.os_draw_technic == 'GPU':
            sc.draw_gpu_toggle = True


class OS_PT_UI_Panel(Panel):

    bl_label = "Mesh Onion Skins"
    bl_space_type = 'VIEW_3D'
    bl_region_type = "UI"
    bl_category = "Animation"

    def __init__(self):
        OS_Initialization()
        # check_draw_gpu_toggle()

    @classmethod
    def poll(self, context):

        if len(context.selected_objects) != 1:
            return False
        if context.selected_objects[0] != context.active_object:
            return False
        mode = context.mode

        try:
            if ((context.selected_objects[0].type == 'MESH') or (
                    context.active_object.type == 'ARMATURE')) and (
                    mode == 'OBJECT' or mode == 'POSE'):
                return context.active_object
        except (IndexError, AttributeError) as e:
            return False

    def draw(self, context):
        layout = self.layout
        params = bpy.context.window_manager.onionSkinsParams
        obj = bpy.context.selected_objects[0]
        sc = bpy.context.scene.onion_skins_scene_props
        Skins = sc.onionsk_Skins_count
        onionsk = obj.is_onionsk
        actions = actions_check(obj)
        mp = obj.animation_visualization.motion_path
        if context.mode == 'POSE':
            mp = obj.pose.animation_visualization.motion_path

        if not actions:
            return None
        row = layout.row(align=True)
        row.prop(sc, 'os_draw_technic', text='')
        row = layout.row(align=True)
        row.scale_y = 1.2
        if sc.onionsk_mpath:
            row.operator('mos_op.update_motion_path', text='', icon='IPO_ELASTIC')
        if sc.onionsk_mpath and mp.has_motion_paths:
            row.operator('mos_op.clear_motion_path', text='', icon='X')
        if not onionsk:
            row.operator('mos_op.make_skins', text='Create ', icon='ONIONSKIN_ON')
            if sc.os_draw_technic == 'MESH':
                row.prop(params, 'display_progress', text='', icon='TEMP')
            if (sc.onionsk_Markers_count > 0 and obj.is_os_marker) and\
                    sc.os_draw_technic == 'GPU':
                row.prop(sc, 'draw_gpu_toggle', text='', icon='RENDER_ANIMATION')
        else:
            row.operator('mos_op.make_skins', text='Update ', icon='ONIONSKIN_ON')
            if sc.os_draw_technic == 'GPU':
                row.prop(sc, 'draw_gpu_toggle', text='', icon='RENDER_ANIMATION')
            else:
                row.prop(params, 'display_progress', text='', icon='TEMP')
            if Skins:
                row.operator('mos_op.remove_skins', text='', icon='X')
        row = layout.row(align=True)
        row.operator('mos_op.add_marker', icon='ADD')
        if (sc.onionsk_Markers_count > 0 and obj.is_os_marker is True):
            row.operator('mos_wm.delete_selected_markers', text='', icon='LONGDISPLAY')
            row.operator('mos_op.remove_marker', text='', icon='X')


class OS_PT_Frames_Panel(Panel):

    bl_label = "Frames"
    bl_space_type = 'VIEW_3D'
    bl_region_type = "UI"
    bl_parent_id = "OS_PT_UI_Panel"

    @classmethod
    def poll(self, context):

        if len(context.selected_objects) != 1:
            return False
        if context.selected_objects[0] != context.active_object:
            return False
        try:
            obj = context.active_object
            actions = actions_check(obj)
            if actions:
                return True
        except:
            pass

    def draw(self, context):
        obj = bpy.context.selected_objects[0]
        sc = bpy.context.scene.onion_skins_scene_props
        actions = actions_check(obj)

        if not actions:
            return {'FINISHED'}
        layout = self.layout
        row = layout.row()
        row.prop(sc, "onionsk_method", text="Method")
        if sc.onionsk_method == 'FRAME':
            col = layout.column(align=True)
            split = layout.split()
            row = layout.row()

            row = split.row(align=True)
            row.prop(sc, "onionsk_fr_before", text="Before")
            row.prop(sc, "onionsk_fr_after", text="After")
            row.prop(sc, "onionsk_frame_step", text="Step")

        if sc.onionsk_method == 'KEYFRAME':
            row = layout.row()
            row.prop(sc, "use_all_keyframes")
            col = layout.column(align=True)
            split = layout.split()
            row = layout.row()

            row = split.row(align=True)
            row.enabled = not sc.use_all_keyframes
            row.prop(sc, "onionsk_kfr_before", text="Before")
            row.prop(sc, "onionsk_kfr_after", text="After")

        if sc.onionsk_method == 'SCENE':
            row = layout.row()
            row.prop(sc, "onionsk_fr_sc", toggle=True)
                # text="Playback range (" + str(bpy.context.scene.frame_start) + "-" + str(bpy.context.scene.frame_end) + ")"
            row.prop(sc, "onionsk_action_range", toggle=True)
            col = layout.column(align=True)
            split = layout.split()
            row = layout.row()

            if sc.onionsk_fr_sc or sc.onionsk_action_range:
                row = split.row(align=True)
                row.prop(sc, "onionsk_skip", text="Frame Step")
            else:
                row = split.row(align=True)
                row.prop(sc, "onionsk_fr_start", text="Start")
                row.prop(sc, "onionsk_fr_end", text="End")
                row.prop(sc, "onionsk_skip", text="Step")


class OS_PT_Options_Panel(Panel):

    bl_label = "Options"
    bl_space_type = 'VIEW_3D'
    bl_region_type = "UI"
    bl_parent_id = "OS_PT_UI_Panel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(self, context):

        if len(context.selected_objects) != 1:
            return False
        if context.selected_objects[0] != context.active_object:
            return False
        obj = context.active_object
        actions = actions_check(obj)
        if actions:
            return True

    def draw(self, context):
        layout = self.layout
        params = bpy.context.window_manager.onionSkinsParams
        obj = bpy.context.selected_objects[0]
        sc = bpy.context.scene.onion_skins_scene_props
        actions = actions_check(obj)
        if not actions:
            return {'FINISHED'}
        box = layout.box()
        col = box.column(align=True)
        row = box.row()
        col.label(text="Onion Skins Settings:")
        if sc.os_draw_technic == 'MESH':
            row.prop(sc, "show_in_render")
            row.prop(sc, "os_selectable")
            row = box.row()
            row.prop(sc, "onionsk_colors", text="Colors")
            row.prop(sc, "onionsk_wire", text="Wireframe")
        elif sc.os_draw_technic == 'GPU':
            row.prop(sc, "gpu_flat_colors")
            row.prop(sc, "gpu_colors_in_front")
            row = box.row()
            row.prop(sc, "gpu_mask_oskins")
            row.prop(sc, "gpu_mask_markers")
        row = box.row()
        row.prop(sc, "onionsk_tmarker", text="Time Marker")
        row.prop(sc, "onionsk_mpath", text="Motion Path")
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Selected Object Properties:")
        row = box.row()
        if obj.type == 'MESH':
            if obj.show_in_front is True and params.mesh_inFront is False:
                params.mesh_inFront = True
            if obj.show_in_front is False and params.mesh_inFront is True:
                params.mesh_inFront = False
            if obj.show_wire is True and params.mesh_wire is False:
                params.mesh_wire = True
            if obj.show_wire is False and params.mesh_wire is True:
                params.mesh_wire = False
        row.prop(params, "mesh_inFront", text="In Front")
        row.prop(params, "mesh_wire", text="Wireframe")


class OS_PT_Colors_Panel(Panel):

    bl_label = "Colors"
    bl_space_type = 'VIEW_3D'
    bl_region_type = "UI"
    bl_parent_id = "OS_PT_UI_Panel"
    # bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(self, context):
        if len(context.selected_objects) != 1:
            return False
        if context.selected_objects[0] != context.active_object:
            return False
        return True

    def draw(self, context):
        layout = self.layout
        params = bpy.context.window_manager.onionSkinsParams
        obj = bpy.context.selected_objects[0]
        sc = bpy.context.scene.onion_skins_scene_props
        onionsk = obj.is_onionsk
        actions = actions_check(obj)
        try:
            mat1 = bpy.data.materials[MAT_PREFIX + SUFFIX_before]
            mat2 = bpy.data.materials[MAT_PREFIX + SUFFIX_after]
            mat3 = bpy.data.materials[MAT_PREFIX + SUFFIX_marker]
        except KeyError:
            pass
        shading = bpy.context.space_data.shading
        if params.color_type != 'MATERIAL' and shading.color_type == 'MATERIAL':
            params.color_type = 'MATERIAL'
        if params.color_type != 'TEXTURE' and shading.color_type == 'TEXTURE':
            params.color_type = 'TEXTURE'
        if params.color_type != 'OBJECT' and shading.color_type == 'OBJECT':
            params.color_type = 'OBJECT'
        box = layout.box()
        box.grid_flow(columns=3, align=True).prop(params, "color_type", expand=True)
        flow = box.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=False, align=True)
        col = flow.column(align=True)
        col.label(text="Before")
        col.prop(sc, 'mat_color_bf', text='')  # , text="Before"
        col = flow.column(align=True)
        col.label(text="After")
        col.prop(sc, 'mat_color_af', text='')  # , text="After"
        col = flow.column(align=True)
        col.label(text="Marker")
        col.prop(sc, 'mat_color_m', text='')
        col = flow.column(align=True)
        col.prop(bpy.context.space_data.shading, "show_object_outline", text="Outline")
        col.prop(bpy.context.space_data.shading, "object_outline_color", text="")
        flow = box.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=False, align=True)
        col = flow.column(align=True)
        col.prop(sc, 'color_alpha', text='Alpha', toggle=True)
        col.prop(sc, 'color_alpha_value', text='')
        col = flow.column(align=True)
        col.prop(sc, 'fade_to_alpha', text='Fade', toggle=True)
        col.prop(sc, 'fade_to_value', text='')


class OS_PT_Selection_Panel(Panel):

    bl_label = "Selection"
    bl_space_type = 'VIEW_3D'
    bl_region_type = "UI"
    bl_parent_id = "OS_PT_UI_Panel"
    # bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(self, context):

        if len(context.selected_objects) != 1:
            return False
        if context.selected_objects[0] != context.active_object:
            return False
        set_object_data_collection_items()
        return True

    def draw(self, context):
        layout = self.layout
        params = bpy.context.window_manager.onionSkinsParams
        obj = bpy.context.selected_objects[0]
        sc = bpy.context.scene.onion_skins_scene_props
        Skins = sc.onionsk_Skins_count
        onionsk = obj.is_onionsk
        actions = actions_check(obj)

        obj_child = 0
        try:
            for ob in obj.children:
                if ob.type == "MESH":
                    obj_child = obj_child + 1
        except AttributeError:
            pass

        box = layout.box()
        row = box.row(align=True)
        row.prop(sc, "selection_sets", expand=True)

        col = box.column().split()
        col.label(icon='RESTRICT_SELECT_OFF', text="Selected:  " + str(obj.type) + ": " + str(obj.name))
        if sc.selection_sets == "COLLECTION":
            row = box.row(align=True)
            row.prop(sc, "show_parent_users_collection", text='', icon='FILE_PARENT')
            row.prop(params, "active_obj_users_collection", text='', expand=False)

        if obj.type == 'ARMATURE' and sc.selection_sets == "PARENT":
            col = box.column().split()
            if obj_child > 0:
                col.label(icon='LINKED', text="Parented:  " + str(obj_child) + " skinnable meshes")
            else:
                col.label(icon='UNLINKED', text="Parented:  None of skinnable meshes")

        elif sc.selection_sets == "PARENT":
            col = box.column().split()
            if obj.parent:
                col.label(icon='LINKED', text="Parent:  " + str(obj.parent.type) + ": " + str(obj.parent.name))
            else:
                col.label(icon='UNLINKED', text="Parent:  None")
        wm = bpy.context.window_manager
        row = box.row()
        row.template_list("OBJECT_UL_Childrens", "", wm, "os_childrens_collection", wm, "active_os_object_list")
        col = row.column()
        col.menu("WM_MT_List_ops_menu", icon='DOWNARROW_HLT', text="")
        col.operator("wm.os_update_childrens_list", text='', icon='FILE_REFRESH')
        col.operator("wm.os_uncheck_all_children_list", text='', icon='CHECKBOX_DEHLT')
        col.operator("wm.os_check_all_children_list", text='', icon='CHECKMARK')  # CHECKBOX_HLT
        row = box.row()
        row.prop(params, "highlight_active_os_object_list", toggle=True)

        box = layout.box()
        if not actions:
            col = box.column().split()
            col.label(icon="CANCEL", text="Not Animated")
        else:
            col = box.column().split()
            col.label(icon='FCURVE', text="Is Animated")

        if actions and not onionsk:
            col.label(icon="X", text="Not Using")
        if actions and onionsk:
            col.label(icon='ONIONSKIN_ON', text="Using Skins")

        box = layout.box()
        row = box.row(align=True)
        try:
            row.label(icon="NONE", text="Onion Objects: " + str(Skins))
            row.label(icon="NONE", text="Marker Objects: " + str(sc.onionsk_Markers_count))
        except AttributeError:
            pass


class OBJECT_UL_Childrens(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            if item:
                layout.prop(item, "name", text="", emboss=False)
                if item.flag:
                    layout.prop(item, "flag", text="", emboss=False, icon='CHECKBOX_HLT')
                else:
                    layout.prop(item, "flag", text="", emboss=False, icon='CHECKBOX_DEHLT')
            else:
                layout.label(text="", translate=False)
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="")  # icon_value=icon


class OS_PT_View_Range_Panel(Panel):

    bl_label = "View Range"
    bl_space_type = 'VIEW_3D'
    bl_region_type = "UI"
    bl_parent_id = "OS_PT_Frames_Panel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(self, context):

        if len(context.selected_objects) != 1:
            return False
        if context.selected_objects[0] != context.active_object:
            return False
        set_object_data_collection_items()
        return True

    def draw_header(self, context):
        sc = bpy.context.scene.onion_skins_scene_props
        layout = self.layout
        layout.prop(sc, 'view_range', text='')

    def draw(self, context):
        sc = bpy.context.scene.onion_skins_scene_props
        layout = self.layout
        row = layout.row(align=True)
        if sc.os_draw_technic == 'GPU' and sc.onionsk_method == 'KEYFRAME':
            row.prop(sc, 'view_range_frame_type', expand=True)
        row = layout.row(align=True)
        row.prop(sc, 'view_before')
        row.prop(sc, 'view_after')


class OS_PT_FilterKeys_Panel(Panel):

    bl_label = "Filter Keyframes"
    bl_space_type = 'VIEW_3D'
    bl_region_type = "UI"
    bl_parent_id = "OS_PT_Frames_Panel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(self, context):

        sc = bpy.context.scene.onion_skins_scene_props
        if sc.onionsk_method == 'KEYFRAME':
            return sc.onionsk_method

    def draw_header(self, context):
        # params = bpy.context.window_manager.onionSkinsParams
        sc = bpy.context.scene.onion_skins_scene_props
        layout = self.layout
        layout.prop(sc, 'filter_keyframes', text='')

    def draw(self, context):
        sc = bpy.context.scene.onion_skins_scene_props
        layout = self.layout
        col = layout.column()
        col.prop(sc, 'filter_active_bone', icon='BONE_DATA')
        col = layout.column(align=True)
        col.label(text='Keyframe Type:')
        col.prop(sc, 'key_type_keyframe', icon='KEYTYPE_KEYFRAME_VEC')
        col.prop(sc, 'key_type_breakdown', icon='KEYTYPE_BREAKDOWN_VEC')
        col.prop(sc, 'key_type_movinghold', icon='KEYTYPE_MOVING_HOLD_VEC')
        col.prop(sc, 'key_type_extreme', icon='KEYTYPE_EXTREME_VEC')
        col.prop(sc, 'key_type_jitter', icon='KEYTYPE_JITTER_VEC')


class OS_PT_Visibility_Panel(Panel):

    bl_label = "Visibility"
    bl_space_type = 'VIEW_3D'
    bl_region_type = "UI"
    bl_parent_id = "OS_PT_UI_Panel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(self, context):
        if len(context.selected_objects) != 1:
            return False
        if context.selected_objects[0] != context.active_object:
            return False
        try:
            obj = bpy.context.active_object
            if obj.is_onionsk or obj.is_os_marker:
                return True
        except:
            pass

    def draw(self, context):
        sc = bpy.context.scene.onion_skins_scene_props
        layout = self.layout
        lcol = layout.column(align=True)
        flow = lcol.grid_flow(columns=3, align=True)
        flow.prop(sc, "hide_os_before", text='Before', toggle=True)
        flow.prop(sc, "hide_os_after", text='After', toggle=True)
        flow.prop(sc, "hide_os_marker", text='Markers', toggle=True)
        col = lcol.column(align=True)
        col.prop(sc, "hide_os_all", text='All', toggle=True)


panels = (
    OS_PT_UI_Panel,
    OS_PT_Frames_Panel,
    OS_PT_Options_Panel,
    OS_PT_Colors_Panel,
    OS_PT_Selection_Panel,
    OS_PT_FilterKeys_Panel,
    OS_PT_View_Range_Panel,
    OS_PT_Visibility_Panel,
)


def update_panel(self, context):
    for panel in panels:
        if "bl_rna" in panel.__dict__:
            bpy.utils.unregister_class(panel)

    for panel in panels:
        prefs = context.preferences.addons[__name__].preferences
        panel.bl_category = prefs.category
        bpy.utils.register_class(panel)


def init_os_collection():
    try:
        empty = bpy.data.objects[OS_empty_name]
    except KeyError:
        bpy.ops.view3d.snap_cursor_to_center()
        coll = bpy.data.collections.new(name=OS_collection_name)
        bpy.context.scene.collection.children.link(coll)
        bpy.ops.object.add(type="EMPTY")
        empty = bpy.context.selected_objects[0]
        empty.name = OS_empty_name
        parent_collection = empty.users_collection[0]
        parent_collection.objects.unlink(empty)
        coll.objects.link(empty)
        empty.hide_set(True)
        empty.hide_render = 1
        empty.hide_select = 1
        empty.select_set(False)
    return empty


def create_skins_empty(obj, skin_type):

    if skin_type == 'ONION':
        empty_name = ("onionsk_" + obj.name)
    if skin_type == 'MARKER':
        empty_name = ("onionsk_M_"+obj.name)
    try:
        e = bpy.data.objects[empty_name]
    except KeyError:
        if not bpy.context.view_layer.layer_collection.children[OS_collection_name].is_visible:
            return None
        bpy.ops.view3d.snap_cursor_to_center()
        bpy.ops.object.add(type="EMPTY")
        e = bpy.context.selected_objects[0]
        e.name = empty_name
        e.select_set(False)
        # make the EMPTY a child of the main empty
        e.parent = bpy.data.objects[OS_empty_name]
        parent_collection = e.users_collection[0]
        parent_collection.objects.unlink(e)
        bpy.data.collections[OS_collection_name].objects.link(e)
        try:
            e.hide_set(True)
        except RuntimeError:
            return None
        e.hide_render = 1
        e.hide_select = 1
    return e


def format_os_material(mat, color):
    mat.diffuse_color = color  # (0.1, 0.1, 1, 0.3)
    mat.roughness = 1
    mat.blend_method = 'BLEND'
    mat.shadow_method = 'NONE'
    mat.show_transparent_back = False
    mat.use_nodes = True
    nodes = get_material_BSDFs(mat)  # "Principled BSDF"
    for n in nodes:
        mat.node_tree.nodes[n].inputs[0].default_value = mat.diffuse_color
        mat.node_tree.nodes[n].inputs[5].default_value = 0
        mat.node_tree.nodes[n].inputs[7].default_value = mat.roughness
        mat.node_tree.nodes[n].inputs[18].default_value = 0.3


def create_skins_materials():
    sc = bpy.context.scene.onion_skins_scene_props
    try:
        m = bpy.data.materials[MAT_PREFIX + SUFFIX_before]
    except KeyError:
        bpy.data.materials.new(MAT_PREFIX + SUFFIX_before)
        m = bpy.data.materials[MAT_PREFIX + SUFFIX_before]
        format_os_material(m, sc.mat_color_bf)
        m.use_fake_user = True
    try:
        m = bpy.data.materials[MAT_PREFIX + SUFFIX_after]
    except KeyError:
        bpy.data.materials.new(MAT_PREFIX + SUFFIX_after)
        m = bpy.data.materials[MAT_PREFIX + SUFFIX_after]
        format_os_material(m, sc.mat_color_af)
        m.use_fake_user = True
    try:
        m = bpy.data.materials[MAT_PREFIX + SUFFIX_marker]
    except KeyError:
        bpy.data.materials.new(MAT_PREFIX + SUFFIX_marker)
        m = bpy.data.materials[MAT_PREFIX + SUFFIX_marker]
        format_os_material(m, sc.mat_color_m)
        m.use_fake_user = True


def dublicate_own_material(obj_name):
    try:
        mat = bpy.data.materials[MAT_PREFIX + obj_name + '_' + SUFFIX_own]
        return mat
    except KeyError:
        try:
            mat = bpy.data.objects[obj_name].data.materials[0].copy()
            mat.name = MAT_PREFIX + obj_name + '_' + SUFFIX_own
        except (IndexError, AttributeError) as e:
            bpy.data.materials.new(MAT_PREFIX + obj_name + '_' + SUFFIX_own)
            mat = bpy.data.materials[MAT_PREFIX + obj_name + '_' + SUFFIX_own]
        mat.blend_method = 'BLEND'
        mat.shadow_method = 'NONE'
        mat.show_transparent_back = False
        mat.use_nodes = True
    return mat


def apply_color_to_skin(obj, at_frame, current_frame, skin_type='ONION'):

    obj.data.materials.clear()
    if skin_type == 'ONION':
        if (at_frame < current_frame):
            obj.data.materials.append(bpy.data.materials[MAT_PREFIX + SUFFIX_before])
        else:
            obj.data.materials.append(bpy.data.materials[MAT_PREFIX + SUFFIX_after])
    if skin_type == 'MARKER':
        obj.data.materials.append(bpy.data.materials[MAT_PREFIX + SUFFIX_marker])

    if skin_type == 'ONION':
        if (at_frame < current_frame):
            obj.color = bpy.data.materials[MAT_PREFIX + SUFFIX_before].diffuse_color
        else:
            obj.color = bpy.data.materials[MAT_PREFIX + SUFFIX_after].diffuse_color
    if skin_type == 'MARKER':
        obj.color = bpy.data.materials[MAT_PREFIX + SUFFIX_marker].diffuse_color

    if skin_type == 'OWN':
        try:
            obj.data.materials[0] = \
                bpy.data.materials[MAT_PREFIX + list_to_str(obj.name.split('_')[1:-1], '_') + '_' + SUFFIX_own]
        except (KeyError, IndexError) as e:
            try:
                obj.data.materials.append(
                    bpy.data.materials[MAT_PREFIX + list_to_str(obj.name.split('_')[1:-1], '_') + '_' + SUFFIX_own])
            except KeyError:
                mat = dublicate_own_material(list_to_str(obj.name.split('_')[1:-1], '_'))
                try:
                    obj.data.materials[0] = mat
                except IndexError:
                    obj.data.materials.append(mat)


def get_material_BSDFs(material):
    nodes = []
    for node in material.node_tree.nodes.items():
        if node[0].split('.')[0] != "Principled BSDF":
            continue
        nodes.append(node[0])
    return nodes


def set_material_alpha(material, alpha):
    material.diffuse_color[3] = alpha
    nodes = get_material_BSDFs(material)
    for n in nodes:
        material.node_tree.nodes[n].inputs[0].default_value[3] = alpha
        material.node_tree.nodes[n].inputs[18].default_value = alpha


def set_material_color(material, color):
    material.diffuse_color = color
    nodes = get_material_BSDFs(material)
    for n in nodes:
        material.node_tree.nodes[n].inputs[0].default_value = color
        material.node_tree.nodes[n].inputs[18].default_value = color[3]


def get_prefix_material_color(skin_prefix):
    sc = bpy.context.scene.onion_skins_scene_props
    if skin_prefix == 'before':
        mat_color = sc.mat_color_bf
    if skin_prefix == 'after':
        mat_color = sc.mat_color_af
    if skin_prefix == 'marker':
        mat_color = sc.mat_color_m
    return mat_color


def get_own_mat_color(obj_name):
    try:
        m = bpy.data.materials[MAT_PREFIX + obj_name + '_' + SUFFIX_own]
    except KeyError:
        return False
    return m.diffuse_color


def make_own_materials(obj):
    if (obj.type == "MESH"):
        dublicate_own_material(obj.name)
    childrens = bpy.context.window_manager.os_childrens_collection
    for i in childrens:
        if not i.flag:
            continue
        dublicate_own_material(i.name)


def get_base_material(skin_prefix):
    try:
        if skin_prefix == 'before':
            m = bpy.data.materials[MAT_PREFIX + SUFFIX_before]
        if skin_prefix == 'after':
            m = bpy.data.materials[MAT_PREFIX + SUFFIX_after]
        if skin_prefix == 'marker':
            m = bpy.data.materials[MAT_PREFIX + SUFFIX_marker]
        return m
    except KeyError:
        return False


def update_base_material(skin_prefix, tree, alpha):
    sc = bpy.context.scene.onion_skins_scene_props
    set_base_material_colors(skin_prefix)
    if sc.onionsk_colors:
        return None
    for sk in tree.children:
        try:
            m = bpy.data.materials[
                MAT_PREFIX + list_to_str(sk.name.split('_')[1:-1], '_') + '_' + SUFFIX_own]
        except KeyError:
            continue
        set_material_alpha(m, alpha)


def set_skins_material(skin_names_list, skin_prefix, frame_number):
    sc = bpy.context.scene.onion_skins_scene_props
    params = bpy.context.window_manager.onionSkinsParams
    mat_color = get_prefix_material_color(skin_prefix)
    if sc.onionsk_colors is False:
        for n in skin_names_list:
            try:
                mat = bpy.data.materials[MAT_PREFIX + n + '_' + str(frame_number)]
            except KeyError:
                mat = False
            if mat:
                set_material_alpha(mat, sc.color_alpha_value)
            else:
                try:
                    mat = bpy.data.materials[MAT_PREFIX + n + '_' + SUFFIX_own].copy()
                except KeyError:
                    objp = checkout_parent(bpy.data.objects[n])
                    make_own_materials(objp)
                    mat = bpy.data.materials[MAT_PREFIX + n + '_' + SUFFIX_own].copy()
                mat.name = MAT_PREFIX + n + '_' + str(frame_number)
                mat.diffuse_color[3] = sc.color_alpha_value
                format_os_material(mat, mat.diffuse_color)
    else:
        try:
            mat = bpy.data.materials[MAT_PREFIX + str(frame_number)]
        except KeyError:
            mat = False
        if mat:
            set_material_color(mat, mat_color)
        else:
            bpy.data.materials.new(MAT_PREFIX + str(frame_number))
            mat = bpy.data.materials[MAT_PREFIX + str(frame_number)]
            format_os_material(mat, mat_color)
    return mat


def get_fade_os_alpha_step(sort_sk_names, mat_color, count):
    sc = bpy.context.scene.onion_skins_scene_props
    params = bpy.context.window_manager.onionSkinsParams
    try:
        if sc.onionsk_colors is False:
            alpha_step = sc.color_alpha_value / ((count / len(sort_sk_names)) - 1)
        else:
            alpha_step = mat_color[3] / ((count / len(sort_sk_names)) - 1)
    except ZeroDivisionError:
        alpha_step = 0
    return alpha_step


def get_fade_os_material(skin):
    sc = bpy.context.scene.onion_skins_scene_props
    if sc.onionsk_colors is False:
        skin_prefix = skin.name.split('_')[0]
        mat = bpy.data.materials[MAT_PREFIX + skin.name.split(skin_prefix + '_')[1]]
    else:
        mat = bpy.data.materials[MAT_PREFIX + skin.name.split('_')[-1]]
    return mat


def get_fade_os_alpha(mat_color, alpha_step, multiply):
    sc = bpy.context.scene.onion_skins_scene_props
    params = bpy.context.window_manager.onionSkinsParams
    if sc.onionsk_colors is False:
        alpha = sc.color_alpha_value - (alpha_step * multiply)
    else:
        alpha = mat_color[3] - (alpha_step * multiply)
    return alpha


def get_fade_skin_object(name, view_range=False):
    if not view_range:
        s = bpy.data.objects[name]
    else:
        try:
            s = bpy.data.objects['after_' + name.split(name.split('_')[0] + '_')[1]]
        except KeyError:
            s = bpy.data.objects['before_' + name.split(name.split('_')[0] + '_')[1]]
    return s


def fade_onion_colors(sk_names, skin_prefix, mat_color, count, view_range=False):
    sc = bpy.context.scene.onion_skins_scene_props
    sort_sk_names = [list_to_str(n.split('_')[1:-1], '_') for n in sk_names]
    sort_sk_names = list(set(sort_sk_names))
    frame_numbers = [int(f.split('_')[-1]) for f in sk_names]
    frame_numbers = list(set(frame_numbers))
    frame_numbers.sort()
    for fn in frame_numbers:
        mat = set_skins_material(sort_sk_names, skin_prefix, fn)
        alpha_step = get_fade_os_alpha_step(sort_sk_names, mat_color, count)
    for sk_name in sort_sk_names:  # bare name (Cube)
        if skin_prefix == 'before':
            multiply = ((count / len(sort_sk_names)) - 1)
        if skin_prefix == 'after':
            multiply = 0
        sk_frame_names = [skin_prefix + '_' + sk_name + '_' + str(fn) for fn in frame_numbers]
        for n in sk_frame_names:  # skinprefix_name_framenumber# (before_Cube_10)
            s = get_fade_skin_object(n, view_range)
            mat = get_fade_os_material(s)
            s.data.materials[0] = mat
            if multiply == 0:
                if skin_prefix == 'after':
                    multiply = multiply + 1
                continue
            alpha = get_fade_os_alpha(mat_color, alpha_step, multiply)
            mat.diffuse_color[3] = alpha
            mat.node_tree.nodes["Principled BSDF"].inputs[18].default_value = alpha
            s.color[3] = s.color[3] - (alpha_step * multiply)
            if s.color[3] < sc.fade_to_value:
                alpha = sc.fade_to_value
                if sc.color_alpha_value < sc.fade_to_value:
                    alpha = sc.color_alpha_value
                s.color[3] = alpha
                mat.diffuse_color[3] = alpha
                mat.node_tree.nodes["Principled BSDF"].inputs[18].default_value = alpha
            if skin_prefix == 'before':
                multiply = multiply - 1
            if skin_prefix == 'after':
                multiply = multiply + 1


def update_colors_by_type(skin_type, obj, skin_prefix, fade=False):
    tree = get_empty_objs_tree(obj, skin_type)
    if not tree:
        return False
    sc = bpy.context.scene.onion_skins_scene_props
    mat_color = get_prefix_material_color(skin_prefix)
    if sc.color_alpha:
        set_alpha = sc.color_alpha_value
    else:
        set_alpha = 1
    update_base_material(skin_prefix, tree, set_alpha)
    count = 0
    for s in tree.children:
        if s.name.find(skin_prefix) == 0:
            if sc.onionsk_colors is True:
                s.color = mat_color
            else:
                own_color = get_own_mat_color(list_to_str(s.name.split('_')[1:-1], '_'))
                if own_color:
                    s.color = own_color
                s.color[3] = set_alpha
                mat = s.data.materials[0]
                if mat:
                    set_material_alpha(mat, set_alpha)
            count = count + 1
    if skin_type == 'MARKER':
        return None
    if fade is False:
        return None
    sk_names = [
        sk.name for sk in tree.children
        if sk.name.split('_')[0] == skin_prefix]
    fade_onion_colors(sk_names, skin_prefix, mat_color, count)


def set_onion_colors(onion_color_type, fade=False):
    sc = bpy.context.scene.onion_skins_scene_props
    obj = bpy.context.active_object
    objp = checkout_parent(obj)
    if sc.fade_to_alpha:
        fade = True
    if onion_color_type == 'BEFORE':
        update_colors_by_type('ONION', objp, 'before', fade)
    if onion_color_type == 'AFTER':
        update_colors_by_type('ONION', objp, 'after', fade)
    if onion_color_type == 'MARKER':
        update_colors_by_type('MARKER', objp, 'marker', fade=False)


def apply_decimate_modif(obj, iterations):
    m = obj.modifiers.new("DECIMATE", type="DECIMATE")
    m.decimate_type = "UNSUBDIV"
    m.iterations = iterations
    bpy.ops.object.modifier_apply(modifier="DECIMATE")


def rename_os_mesh(obj, OSkin, at_frame, current_frame, skin_type='ONION'):
    if skin_type == 'ONION':
        if at_frame < current_frame:
            OSkin.name = 'before_' + obj.name + '_' + str(int(at_frame))
        if at_frame >= current_frame:
            OSkin.name = 'after_' + obj.name + '_' + str(int(at_frame))
    if skin_type == 'MARKER':
        OSkin.name = 'marker_' + obj.name + '_' + str(int(at_frame))


def make_duplicate_mesh(obj, parent_empty, at_frame, current_frame):
    sc = bpy.context.scene.onion_skins_scene_props
    params = bpy.context.window_manager.onionSkinsParams
    if obj.type != "MESH":
        return False

    locw = obj.matrix_world
    bpy.ops.object.duplicate()
    try:
        OSkin = bpy.context.selected_objects[0]
        print('OS Dublicate:', obj.name)
    except IndexError:
        print('OS Dublicate:', obj.name, '  <- Skiped')
        return False
    # Animation Data Actions if exists
    try:
        skin_action = OSkin.animation_data.action
    except AttributeError:
        skin_action = False
    try:
        shape_keys_action = OSkin.data.shape_keys.animation_data.action
    except AttributeError:
        shape_keys_action = False
    OSkin.animation_data_clear()
    # Remove Shape Keys before Armature modifier can be applied
    bpy.context.view_layer.objects.active = OSkin
    try:
        shape_keys_name = OSkin.data.shape_keys.name
    except AttributeError:
        shape_keys_name = False
    if shape_keys_name:
        OSkin.shape_key_add(from_mix=True)
        # bpy.data.shape_keys[shape_keys_name].user_clear()
        for k in OSkin.data.shape_keys.key_blocks:
            OSkin.shape_key_remove(k)
        bpy.data.shape_keys[shape_keys_name].user_clear()
    # Apply All Armature modifiers to Skins
    for modif in OSkin.modifiers:
        if modif.type == 'ARMATURE':
            bpy.ops.object.modifier_apply(modifier=modif.name)
        elif modif.type == 'MESH_DEFORM':
            bpy.ops.object.modifier_apply(modifier=modif.name)
    # Remove Actions Copied data if exists
    if skin_action:
        bpy.data.actions.remove(skin_action, do_unlink=True)
    if shape_keys_action and bpy.app.version < (2, 90, 0):
        bpy.data.actions.remove(shape_keys_action, do_unlink=True)  # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    # Clear all parents
    bpy.ops.object.parent_clear(type='CLEAR')
    # Move to exactly same location as original object
    OSkin.matrix_world = locw
    # Deselect the original object
    obj.select_set(False)
    # Move to Onion Skins Collection
    parent_collection = OSkin.users_collection[0]
    parent_collection.objects.unlink(OSkin)
    bpy.data.collections[OS_collection_name].objects.link(OSkin)
    # Make skin a child of the EMPTY
    OSkin.parent = parent_empty
    if sc.os_selectable:
        OSkin.hide_select = False
    else:
        OSkin.hide_select = True
    if sc.show_in_render:
        OSkin.hide_render = False
    else:
        OSkin.hide_render = True
    if sc.onionsk_wire:
        OSkin.show_wire = True
    else:
        OSkin.show_wire = False
    OSkin.onionsk_Skins_count = 0

    return OSkin


def make_skin_mesh_piece(obj, parent_empty, current_frame, at_frame, skin_type='ONION'):
    sc = bpy.context.scene.onion_skins_scene_props
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    Skins = make_duplicate_mesh(obj, parent_empty, at_frame, current_frame)
    if not Skins:
        return False
    rename_os_mesh(obj, Skins, at_frame, current_frame, skin_type)
    # Apply Colors
    if sc.onionsk_colors:
        if skin_type == 'MARKER':
            apply_color_to_skin(Skins, current_frame, current_frame, skin_type)
        else:
            apply_color_to_skin(Skins, at_frame, current_frame)
    else:
        apply_color_to_skin(Skins, at_frame, current_frame, 'OWN')
    Skins.select_set(False)
    obj.select_set(False)
    return True


def make_onionSkin_frame(self, obj, parent_empty, current_frame, at_frame, skin_type='ONION'):
    Skins_count = 0
    if obj.type == "MESH":
        dublicate_own_material(obj.name)
        make = make_skin_mesh_piece(obj, parent_empty, current_frame, at_frame, skin_type)
        if make:
            Skins_count = Skins_count + 1
    childrens = bpy.context.window_manager.os_childrens_collection
    for i in childrens:
        if not i.flag:
            continue
        try:
            ob = bpy.context.view_layer.objects[i.name]
        except KeyError:
            print("OS: Object '" + i.name + "' does not exists in the current view layer ( Skiped )")
            continue
        if ob.type == "MESH":
            dublicate_own_material(ob.name)
            make = make_skin_mesh_piece(ob, parent_empty, current_frame, at_frame, skin_type)
            if make:
                Skins_count = Skins_count + 1
    return Skins_count


def bake_gpu_mesh_piece(obj, curframe, at_frame, skin_type=''):
    global SHADER
    depsgraph = bpy.context.evaluated_depsgraph_get()
    tmp_obj_pose = obj.evaluated_get(depsgraph)
    mesh = tmp_obj_pose.to_mesh()
    mesh.update()
    mesh.update()
    position = Matrix(obj.matrix_world)
    mesh.transform(position)
    mesh.update()
    mesh.calc_loop_triangles()
    mesh.update()

    vertices = np.empty((len(mesh.vertices), 3), 'f')
    indices = np.empty((len(mesh.loop_triangles), 3), 'i')
    mesh.vertices.foreach_get(
        "co", np.reshape(vertices, len(mesh.vertices) * 3))
    mesh.loop_triangles.foreach_get(
        "vertices", np.reshape(indices, len(mesh.loop_triangles) * 3))
    batch = batch_for_shader(SHADER, 'TRIS', {"pos": vertices}, indices=indices)
    objp = checkout_parent(bpy.context.active_object)
    if skin_type == 'MARKER':
        global GPU_MARKERS
        GPU_MARKERS[objp.name][obj.name + '|@|' + str(at_frame)] = batch
    else:
        global GPU_FRAMES
        GPU_FRAMES[objp.name][obj.name + '|@|' + str(at_frame)] = batch
    return True


def make_gpu_frame(obj, curframe, at_frame, skin_type=''):
    Skins_count = 0
    if obj.type == "MESH":
        bake = bake_gpu_mesh_piece(obj, curframe, at_frame, skin_type)
        if bake:
            Skins_count = Skins_count + 1
    childrens = bpy.context.window_manager.os_childrens_collection
    for i in childrens:
        if not i.flag:
            continue
        try:
            ob = bpy.context.view_layer.objects[i.name]
        except KeyError:
            print("OS: Object '" + i.name + "' does not exists in the current view layer ( Skiped )")
            continue
        if ob.type == "MESH":
            bake = bake_gpu_mesh_piece(ob, curframe, at_frame, skin_type)
            if bake:
                Skins_count = Skins_count + 1
    return Skins_count


def remove_time_markers():
    tmarkers = bpy.context.scene.timeline_markers
    #Remove timeline_markers
    for m in tmarkers:
        if m.name == 'os':
            tmarkers.remove(m)


def remove_motion_paths():
    #!!!!!!!!!!!!!!SET TO CONTEXT OBJECT MODE !!!!!!!!!!!!!!!!!
    #Store current mode to return to it after complete operations
    mode = bpy.context.mode
    bpy.ops.object.mode_set(mode='OBJECT')
    #Remove Motion paths
    if mode == 'POSE':
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.pose.paths_clear(only_selected=False)
        bpy.ops.object.mode_set(mode=mode)
    else:
        bpy.ops.object.paths_clear(only_selected=False)
    bpy.ops.object.mode_set(mode=mode)


def remove_materials(objp, obj_tree, skin_type='ONION'):
    onion_mats = [
        mat for mat in bpy.data.materials
        if text_lookup(MAT_PREFIX, mat.name)
    ]
    for om in onion_mats:
        #  Remove '_own' materials
        if text_lookup(SUFFIX_own, om.name):
            if text_lookup(objp.name, om.name):
                if om.users == 0:
                    bpy.data.materials.remove(om, do_unlink=True)
                    continue
            childrens = childrens_lookup(objp)
            for ob_owner in childrens:
                if text_lookup(ob_owner.name, om.name):
                    if om.users == 0:
                        bpy.data.materials.remove(om, do_unlink=True)
                        break
        #  Remove every onion_skins materials except...
        elif not text_lookup(SUFFIX_before, om.name) and\
                not text_lookup(SUFFIX_after, om.name) and\
                not text_lookup(SUFFIX_marker, om.name) and\
                not text_lookup(SUFFIX_own, om.name):
            if om.users == 0:
                bpy.data.materials.remove(om, do_unlink=True)


def remove_mesh_data(obj_tree):
    params = bpy.context.window_manager.onionSkinsParams
    ch = 0
    for x in obj_tree.children:
        mesh = x.data
        bpy.data.objects.remove(x, do_unlink=True)
        if bpy.data.meshes[mesh.name].users == 0:
            bpy.data.meshes.remove(mesh)
        ch = ch + 1
    return ch


def remove_skins(obj, skin_type='ONION'):
    sc = bpy.context.scene.onion_skins_scene_props
    objp = checkout_parent(obj)
    ch = 0
    tree = 0
    try:
        if skin_type == 'ONION':
            tree = bpy.data.objects["onionsk_"+obj.name]
        if skin_type == 'MARKER':
            tree = bpy.data.objects["onionsk_M_"+obj.name]
    except KeyError:
        pass
    # Remove a tree of skins if active object is not armature or it has no parents
    try:
        if objp.name != obj.name:
            if skin_type == 'ONION':
                tree = bpy.data.objects["onionsk_"+objp.name]
            if skin_type == 'MARKER':
                tree = bpy.data.objects["onionsk_M_"+objp.name]
    except KeyError:
        pass

    if tree:
        ch = remove_mesh_data(tree)
        remove_materials(objp, tree, skin_type)
        bpy.data.objects.remove(tree, do_unlink=True)

    if skin_type == 'ONION':
        objp.onionsk_Skins_count = 0
        obj.is_onionsk = 0
        objp.is_onionsk = 0
        for ob in objp.children:
            ob.onionsk_Skins_count = 0
            ob.is_onionsk = 0
    if skin_type == 'MARKER':
        sc.onionsk_Markers_count = sc.onionsk_Markers_count - ch
        obj.is_os_marker = 0
        objp.is_os_marker = 0


def run_filter_keyframes(key):
    skip = False
    sc = bpy.context.scene.onion_skins_scene_props
    if sc.key_type_keyframe is False:
        if key.type == 'KEYFRAME':
            skip = True
    if sc.key_type_breakdown is False:
        if key.type == 'BREAKDOWN':
            skip = True
    if sc.key_type_movinghold is False:
        if key.type == 'MOVING_HOLD':
            skip = True
    if sc.key_type_extreme is False:
        if key.type == 'EXTREME':
            skip = True
    if sc.key_type_jitter is False:
        if key.type == 'JITTER':
            skip = True

    return skip


def run_filter_active_bone(obj, fcurve):
    if obj.type == 'MESH':
        return False
    active_bone = obj.data.bones.active
    try:
        if fcurve.data_path.split('"')[1] != active_bone.name:
            skip = True
        else:
            skip = False
    except (AttributeError, IndexError) as e:
        skip = True
    return skip


def create_update_motion_path(context, mode, obj, fs, fe, kfbefore, kfafter):
    sc = context.scene.onion_skins_scene_props
    curframe = context.scene.frame_current
    if sc.onionsk_mpath is False:
        #Remove if option is unchecked
        if (mode == 'POSE'):
            bpy.ops.object.mode_set(mode=mode)
            bpy.ops.pose.paths_clear(only_selected=False)
            bpy.ops.object.mode_set(mode='OBJECT')
        else:
            bpy.ops.object.paths_clear(only_selected=False)
        return None

    #CREATE MOTION PATH
    mp = obj.animation_visualization.motion_path
    if mode == 'POSE':
        bpy.ops.object.mode_set(mode='POSE')
        mp = obj.pose.animation_visualization.motion_path
    if sc.onionsk_method == 'FRAME':
        mp.type = 'CURRENT_FRAME'
        mp.frame_before = sc.onionsk_fr_before
        mp.frame_after = sc.onionsk_fr_after
        mp.frame_step = sc.onionsk_frame_step
        fs = curframe-sc.onionsk_fr_before
    if sc.onionsk_method == 'KEYFRAME':
        bf = sc.onionsk_kfr_before - 1
        af = sc.onionsk_kfr_after - 1
        if sc.use_all_keyframes:
            bf = len(kfbefore)
            af = len(kfafter)
        if (len(kfbefore) - 1) < bf:
            bf = len(kfbefore) - 1
        if (len(kfafter) - 1) < af:
            af = len(kfafter) - 1
        mp.type = 'RANGE'
        mp.frame_start = kfbefore[0]
        mp.frame_end = kfafter[af]
        mp.frame_step = kfafter[af]-kfbefore[0]
        fs = kfbefore[0]
        fe = kfafter[af]
        if bf < 0 or kfbefore[0] == -101010.0:  # NO BEFORE
            mp.frame_start = curframe
            mp.frame_step = kfafter[af]-curframe
            fs = curframe
        if af < 0 or kfafter[0] == 101010.0:  # NO AFTER
            mp.frame_end = curframe
            mp.frame_step = curframe-kfbefore[0]
            fe = curframe
    if sc.onionsk_method == 'SCENE':
        mp.type = 'RANGE'
        mp.frame_start = sc.onionsk_fr_start
        mp.frame_end = sc.onionsk_fr_end
        mp.frame_step = sc.onionsk_skip
    #Remove to Update MPath if already exists
    if mode == 'POSE' and mp.has_motion_paths is True:
        bpy.ops.pose.paths_clear(only_selected=False)
    else:
        if mp.has_motion_paths is True:
            bpy.ops.object.paths_clear(only_selected=False)
    #Calculate New MPath
    if mode == 'POSE' and mp.has_motion_paths is False:
        bpy.ops.pose.paths_calculate(start_frame=fs, end_frame=fe+1)
    else:
        if mp.has_motion_paths is False:
            bpy.ops.object.paths_calculate(start_frame=fs, end_frame=fe + 1)
    bpy.ops.object.mode_set(mode=mode)


def update_in_range_playback(self, context):
    if self.onionsk_fr_sc and self.onionsk_action_range:
        self.onionsk_action_range = False


def update_in_range_action(self, context):
    if self.onionsk_action_range and self.onionsk_fr_sc:
        self.onionsk_fr_sc = False


def update_widget():
    force = False
    sec_since_update = time.time() - Progress_Status.last_updated

    if not force and sec_since_update < Progress_Status.update_every:
        return 0.05

    bpy.types.WorkSpace.status_text_set_internal(None)

    Progress_Status.last_updated = time.time()
    return 0.05


class Progress_Status(object):
    update_every = 0.1  # seconds

    widget_visible = False
    last_updated = 0

    @staticmethod
    def draw(self, context):
        if Progress_Status.get_progress(self, context) < 100:
            self.layout.prop(context.scene, "Status_progress", text="Progress", slider=True)
        else:
            Progress_Status.hide(self)

    @staticmethod
    def create_progress_property(self):
        bpy.types.Scene.Status_progress = bpy.props.IntProperty(
            default=0, min=0, max=100, step=1, subtype='PERCENTAGE')

    @staticmethod
    def set_progress(self, context, value):
        if Progress_Status.widget_visible:
            context.scene.Status_progress = value

    @staticmethod
    def get_progress(self, context):
        if Progress_Status.widget_visible:
            return context.scene.Status_progress
        else:
            return 0

    @staticmethod
    def show(self, context):
        if not Progress_Status.widget_visible:
            Progress_Status.create_progress_property(self)
            bpy.app.timers.register(update_widget)
            bpy.types.STATUSBAR_HT_header.append(Progress_Status.draw)
            Progress_Status.widget_visible = True
            Progress_Status.set_progress(self, context, 0)

    @staticmethod
    def hide(self):
        bpy.types.STATUSBAR_HT_header.remove(Progress_Status.draw)
        bpy.app.timers.unregister(update_widget)
        Progress_Status.widget_visible = False


def remove_handlers(context):
    sc = bpy.context.scene.onion_skins_scene_props
    global Draw_Handler
    sc.draw_gpu_toggle = False
    if Draw_Timer is not None:
        context.window_manager.event_timer_remove(Draw_Timer)
    if Draw_Handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(Draw_Handler, 'WINDOW')
    Draw_Handler = None


class GPU_OT_Draw_Skins(bpy.types.Operator):
    bl_idname = "mos_op.gpu_draw_skins"
    bl_label = "GPU Draw Skins"
    bl_description = "Draw onion skins in 3D Viewport"
    bl_options = {'REGISTER'}

    def __init__(self):
        self.sc = bpy.context.scene.onion_skins_scene_props
        self.params = bpy.context.window_manager.onionSkinsParams
        self._timer = None
        self.draw_handler = None
        self.frames_count = None
        self.before = None
        self.after = None

    def invoke(self, context, event):
        global Draw_Handler
        global Draw_Timer
        if self.sc.os_draw_technic != 'GPU':
            return {'CANCELLED'}
        Draw_Timer = context.window_manager.event_timer_add(0.1, window=context.window)
        Draw_Handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_gpu_frames, (context,), 'WINDOW', 'POST_VIEW')
        context.window_manager.modal_handler_add(self)
        obj = checkout_parent(context.active_object)
        if not GPU_FRAMES.get(obj.name):
            return {'RUNNING_MODAL'}
        self.frames_count = list(set([(int(float(f.split('|@|')[-1])), i) for i, f in enumerate(GPU_FRAMES[obj.name])]))
        self.frames_count.sort()
        self.frames_count = dict(self.frames_count)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):

        if self.sc.draw_gpu_toggle is False:
            remove_handlers(context)
            return {'CANCELLED'}

        return {'PASS_THROUGH'}

    def evaluate_fade(self, colorB, colorA, curframe, item_frame, frame_diff):
        if not self.frames_count:
            return None
        sc = bpy.context.scene.onion_skins_scene_props
        if not sc.view_range:
            if item_frame < curframe:
                bf = [f for f in self.frames_count if f < curframe]
                before_frames = len(bf) - 1
                frame_diff = len([f for f in bf if f >= item_frame])
            else:
                af = [f for f in self.frames_count if f > curframe]
                after_frames = len(af) - 1
                frame_diff = len([f for f in af if f <= item_frame])
        else:
            before_frames = sc.view_before - 1
            after_frames = sc.view_after - 1
            if sc.view_range_frame_type == 'KEYFRAME':
                if item_frame < curframe:
                    bf = [f for f in self.frames_count if f < curframe]
                    bf.reverse()
                    self.before = [f for i, f in enumerate(bf) if i <= before_frames]
                    frame_diff = len([f for f in self.before if f >= item_frame])
                else:
                    af = [f for f in self.frames_count if f > curframe]
                    self.after = [f for i, f in enumerate(af) if i <= after_frames]
                    frame_diff = len([f for f in self.after if f <= item_frame])
        if not sc.fade_to_alpha:
            fade = 0
        elif item_frame < curframe:
            if before_frames <= 0:
                before_frames = 1
            fade = ((colorB[3] - sc.fade_to_value) / before_frames) * (frame_diff - 1)
        else:
            if after_frames <= 0:
                after_frames = 1
            fade = ((colorA[3] - sc.fade_to_value) / after_frames) * (frame_diff - 1)
        return fade

    def draw_gpu_frames(self, context):
        if not context.active_object or not context.space_data.overlay.show_overlays:
            return None
        curframe = context.scene.frame_current
        global SHADER
        sc = bpy.context.scene.onion_skins_scene_props
        obj = checkout_parent(context.active_object)
        colorB = sc.mat_color_bf
        colorA = sc.mat_color_af
        colorM = sc.mat_color_m
        if sc.hide_os_marker and GPU_MARKERS.get(obj.name):
            for item in GPU_MARKERS[obj.name]:
                color = (colorM[0], colorM[1], colorM[2], colorM[3])
                SHADER.bind()
                SHADER.uniform_float("color", color)
                if not sc.gpu_mask_markers:
                    bgl.glDepthMask(False)
                bgl.glEnable(bgl.GL_DEPTH_TEST)
                bgl.glEnable(bgl.GL_CULL_FACE)
                if not sc.gpu_flat_colors:
                    bgl.glEnable(bgl.GL_BLEND)
                if sc.gpu_colors_in_front:
                    bgl.glDepthRange(1, 0)

                GPU_MARKERS[obj.name][item].draw(SHADER)
                bgl.glDisable(bgl.GL_BLEND)
                bgl.glDisable(bgl.GL_CULL_FACE)
                bgl.glDisable(bgl.GL_DEPTH_TEST)

        if not GPU_FRAMES.get(obj.name):
            return None
        for item in GPU_FRAMES[obj.name]:
            item_frame = float(item.split('|@|')[-1])
            # print(item)
            if curframe == item_frame:
                continue
            frame_diff = abs(curframe - item_frame)
            if not sc.view_range:
                draw = True
            else:
                draw = False

            fade = self.evaluate_fade(colorB, colorA, curframe, item_frame, frame_diff)

            if item_frame < curframe:
                color = (colorB[0], colorB[1], colorB[2], colorB[3] - fade)
                if sc.view_range_frame_type == 'KEYFRAME' and sc.hide_os_before:
                    if item_frame in self.before:
                        draw = True
                elif frame_diff <= sc.view_before and sc.hide_os_before:
                    draw = True
            else:
                color = (colorA[0], colorA[1], colorA[2], colorA[3] - fade)
                if sc.view_range_frame_type == 'KEYFRAME' and sc.hide_os_after:
                    if item_frame in self.after:
                        draw = True
                elif frame_diff <= sc.view_after and sc.hide_os_after:
                    draw = True

            if curframe != item_frame and draw:
                SHADER.bind()
                SHADER.uniform_float("color", color)
                if not sc.gpu_mask_oskins:
                    bgl.glDepthMask(False)
                bgl.glEnable(bgl.GL_DEPTH_TEST)
                bgl.glEnable(bgl.GL_CULL_FACE)
                if not sc.gpu_flat_colors:
                    bgl.glEnable(bgl.GL_BLEND)
                if sc.gpu_colors_in_front:
                    bgl.glDepthRange(1, 0)

                GPU_FRAMES[obj.name][item].draw(SHADER)
                bgl.glDisable(bgl.GL_BLEND)
                bgl.glDisable(bgl.GL_CULL_FACE)
                bgl.glDisable(bgl.GL_DEPTH_TEST)

    def finish(self, context):
        self.remove_handlers(context)
        return {'FINISHED'}


class OS_OT_CreateUpdate_Skins(bpy.types.Operator):
    bl_label = 'Update Onion Skins'
    bl_idname = 'mos_op.make_skins'
    bl_description = "Update Mesh Onion Skins for the selected object"
    bl_options = {'REGISTER', 'UNDO'}

    init = False
    mode = None
    obj = None
    objp = None
    empty = None
    inFront_get_value = False
    curframe = None
    fs = 0
    fe = 0
    skip = False
    kfbefore = []
    kfafter = []
    Frames = []
    Skins_count = 0

    _timer = None
    th = None
    prog = 0
    stop_early = False

    loopRange = None
    loopIter = 0
    isReverse = False
    processing = False
    job_done = False

    def __init__(self):
        self.sc = bpy.context.scene.onion_skins_scene_props
        self.params = bpy.context.window_manager.onionSkinsParams
        self.obj = bpy.context.active_object
        self.objp = checkout_parent(self.obj)
        self.mode = bpy.context.mode
        self.curframe = bpy.context.scene.frame_current
        self._timer = None

    def modal(self, context, event):
        global CREATING
        if event.type in {'ESC'}:  # 'RIGHTMOUSE',
            self.cancel(context)

            self.stop_early = True
            self.th.join()
            OS_OT_CreateUpdate_Skins.finishing(self, context)
            CREATING = False
            print('CANCELLED')

            return {'CANCELLED'}

        if event.type == 'TIMER':
            if self.processing:
                OS_OT_CreateUpdate_Skins.make_frame(self, self.Frames[self.loopIter])
                print(str(int(self.prog)) + '%')
                self.processing = False

            if not self.th.isAlive():
                self.th.join()
                OS_OT_CreateUpdate_Skins.finishing(self, context)
                # print('DONE')
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def evaluate_frames(self, obj, curframe, fs, fe, skip, isReverse, exclude):
        sc = bpy.context.scene.onion_skins_scene_props
        global CREATING
        CREATING = True
        Skins_count = 0
        skipthat = False
        if (sc.onionsk_method == 'FRAME'):
            if fs < 0:
                if curframe > 0:
                    skipthat = True
                fs = 0
        # start at frame
        Frame = fs
        lp = int((fe - fs) / skip)

        dolast = False
        if (fs + ((lp) * skip)) != fe:
            lp = lp + 1
            dolast = True
        if isReverse and (fe - ((lp) * skip)) != fs:
            lp = lp + 1

        if isReverse:
            self.loopRange = range((lp), 0, -1)
        else:
            self.loopRange = range(1 + lp)
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~LOOP~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        Frames = []
        for zz in self.loopRange:
            if dolast and zz == lp:
                Frame = fe
            else:
                if isReverse:
                    Frame = (fe - ((zz) * skip))
                    if fs + zz == 0 or Frame < fs:
                        Frame = fs
                else:
                    Frame = fs + ((zz) * skip)
            if sc.onionsk_method == 'FRAME' and Frame == curframe:
                continue
            if skipthat and Frame == skip:
                continue
            if exclude == 1 and Frame == fs:
                continue
            if exclude == 2 and Frame == fe:
                continue
            Frames.append(Frame)
        return Frames

    def os_method_frame(self, objp, curframe, dont_create=False):
        sc = bpy.context.scene.onion_skins_scene_props
        fs = curframe - sc.onionsk_fr_before
        fe = curframe
        if fs < 0:
            fs = 0
        skip = sc.onionsk_frame_step
        if not dont_create:
            FramesBf = self.evaluate_frames(objp, curframe, fs, fe, skip, 1, 0)
        fs = curframe
        fe = curframe + sc.onionsk_fr_after
        if not dont_create:
            FramesAf = self.evaluate_frames(objp, curframe, fs, fe, skip, 0, 0)
            self.fs = fs
            self.fe = fe
            return FramesBf + FramesAf
        return fs, fe

    def get_keyframes(self, obj, action, curframe):
        sc = bpy.context.scene.onion_skins_scene_props
        all_keys = []
        for fcurve in action.fcurves:
            keys = fcurve.keyframe_points
            if sc.filter_keyframes and sc.filter_active_bone and \
                    obj.type == 'ARMATURE':
                bone_fcurve_skip = run_filter_active_bone(obj, fcurve)
                if bone_fcurve_skip:
                    continue
            for key in keys:
                if sc.filter_keyframes:
                    key_skip = run_filter_keyframes(key)
                    if key_skip:
                        continue
                all_keys.append(key.co[0])
        all_keys = list(set(all_keys))
        all_keys.sort()
        kfbefore = [key for key in all_keys if key < curframe]
        kfafter = [key for key in all_keys if key > curframe]
        return kfbefore, kfafter, all_keys

    def os_methos_keyframe(self, obj, objp, curframe, dont_create=False):
        sc = bpy.context.scene.onion_skins_scene_props
        params = bpy.context.window_manager.onionSkinsParams
        bf = sc.onionsk_kfr_before
        af = sc.onionsk_kfr_after
        try:
            action = obj.animation_data.action
        except AttributeError:
            action = objp.animation_data.action
        try:
            if action.fcurves:
                pass
        except AttributeError:
            if not dont_create:
                msg = "Mesh Onion Skins: Keys does not found. Use Edit strip mode of the action."
                self.report({'ERROR'}, msg)
            return False
        kfb_kfa = OS_OT_CreateUpdate_Skins.get_keyframes(self, obj, action, curframe)
        kfbefore = kfb_kfa[0]
        kfafter = kfb_kfa[1]

        if len(kfbefore) == 0 and len(kfafter) == 0:
            if not dont_create:
                msg = "Mesh Onion Skins: Requiered Keyframes does not found."
                self.report({'WARNING'}, msg)
            return False

        if not sc.use_all_keyframes:
            if len(kfbefore) < bf:
                bf = len(kfbefore)
            else:
                if len(kfbefore) - bf > 0:
                    for i in range(len(kfbefore) - bf):
                        kfbefore.pop(0)
            if len(kfafter) < af:
                af = len(kfafter)
            else:
                if len(kfafter) - af > 0:
                    for i in range(len(kfafter) - af):
                        kfafter.pop(-1)
        else:
            all_keys = kfb_kfa[2]
            bf = len([k for k in all_keys if k < curframe])
            af = len([k for k in all_keys if k > curframe])

        if len(kfbefore) == 0:
            kfbefore.append(-101010.0)
            bf = 0
        if len(kfafter) == 0:
            kfafter.append(101010.0)
            af = 0
        if dont_create:
            return kfbefore, kfafter, kfb_kfa[2]

        if (bf > af):
            FramesB = []
            if af > 0:
                for i in range(af):
                    FramesA = self.evaluate_frames(objp, curframe, kfbefore[i], kfafter[i], kfafter[i] - kfbefore[i], 0, 0)
                    FramesB = FramesB + FramesA
            for i in range(af, bf):
                FramesA = self.evaluate_frames(objp, curframe, kfbefore[i], kfafter[len(kfafter) - 1], kfafter[len(kfafter) - 1] - kfbefore[i], 0, 2)
                FramesB = FramesB + FramesA
            Frames = FramesB

        if (bf < af):
            FramesB = []
            if bf > 0:
                for i in range(bf):
                    FramesA = self.evaluate_frames(objp, curframe, kfbefore[i], kfafter[i], kfafter[i] - kfbefore[i], 0, 0)
                    FramesB = FramesB + FramesA
            for i in range(bf, af):
                FramesA = self.evaluate_frames(objp, curframe, kfbefore[len(kfbefore)-1], kfafter[i], kfafter[i]-kfbefore[len(kfbefore)-1], 0, 1)
                FramesB = FramesB + FramesA
            Frames = FramesB
        if (bf == af):
            FramesB = []
            for i in range(af):
                FramesA = self.evaluate_frames(objp, curframe, kfbefore[i], kfafter[i], kfafter[i] - kfbefore[i], 0, 0)
                FramesB = FramesB + FramesA
            Frames = FramesB
        self.kfbefore = kfbefore
        self.kfafter = kfafter
        if sc.use_all_keyframes:
            if float(curframe) in all_keys:
                Frames.append(float(curframe))
        Frames.sort()
        return Frames

    def execute(self, context):

        sc = bpy.context.scene.onion_skins_scene_props
        params = bpy.context.window_manager.onionSkinsParams
        prefs = bpy.context.preferences.addons[__name__].preferences
        obj = context.selected_objects[0]
        global CREATING
        CREATING = True
        #Switch in Front property for display mesh in viewport properly.
        #If u don't then newly created mesh goes on top of it regardless.
        # It will be returned to previouse state at the end of operation.
        self.inFront_get_value = params.mesh_inFront
        params.mesh_inFront = False

        #Remove timeline_markers
        tmarkers = context.scene.timeline_markers
        imarkers = tmarkers.items()
        for m in imarkers:
            if (m[0] == 'os'):
                tmarkers.remove(tmarkers.get('os'))

        bpy.data.objects.update()
        # Check object is a parent or a child
        objp = checkout_parent(obj)

        remove_skins(obj)
        remove_handlers(context)
        global GPU_FRAMES
        try:
            GPU_FRAMES[objp.name].clear()
        except KeyError:
            pass

        #!!!!!!!!!!!!!!SET TO CONTEXT OBJECT MODE !!!!!!!!!!!!!!!!!
        #Store current mode to return to it after complete operations
        mode = bpy.context.mode
        bpy.ops.object.mode_set(mode='OBJECT')
        if sc.os_draw_technic == 'MESH':
            # Initially Create Collectiont for skins to be stored in
            main_empty = init_os_collection()
            # Create an EMPTY using onionsk + Parent object's name
            self.empty = create_skins_empty(objp, 'ONION')
            if not self.empty:
                msg = "Mesh Onion Skins collection or parent Empty is hidden, make sure it is visible in View Layer"
                self.report({'ERROR'}, msg)
                return self.finishing(context)

        # Setup the Colored Materials for Skins
        create_skins_materials()

        obj.select_set(False)
        curframe = context.scene.frame_current

        import threading

        def long_task(self, context):
            i = 0
            while not self.job_done:
                if self.stop_early:
                    return
                if not self.Frames:
                    Progress_Status.hide(self)
                    return
                if not self.processing:
                    time.sleep(.005)
                    self.loopIter = range(len(self.Frames))[i]
                    self.prog = 100 / (len(self.Frames)) * (self.loopIter + 1)
                    Progress_Status.set_progress(self, context, self.prog)
                    i += 1
                    self.processing = True
                if self.prog >= 100:
                    self.job_done = True

        self.th = threading.Thread(target=long_task, args=(self, context))
        OS_OT_CreateUpdate_Skins.set_frames(self, context)
        if sc.os_draw_technic == 'GPU':
            GPU_FRAMES[objp.name] = {}
            params.display_progress = False

        if params.display_progress:
            Progress_Status.show(self, context)
            self.th.start()
            wm = context.window_manager
            self._timer = wm.event_timer_add(0.1, window=context.window)
            wm.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            if not self.Frames:
                OS_OT_CreateUpdate_Skins.finishing(self, context)
                return {'FINISHED'}
            for Frame in self.Frames:
                OS_OT_CreateUpdate_Skins.make_frame(self, Frame)

            OS_OT_CreateUpdate_Skins.finishing(self, context)
            return {'FINISHED'}

    def set_frames(self, context):
        sc = bpy.context.scene.onion_skins_scene_props
        obj = self.obj
        objp = self.objp
        mode = self.mode
        curframe = self.curframe
        if sc.onionsk_method == 'FRAME':
            self.Frames = self.os_method_frame(objp, curframe)
        if sc.onionsk_method == 'SCENE':
            self.fs = sc.onionsk_fr_start
            self.fe = sc.onionsk_fr_end
            self.skip = sc.onionsk_skip
            # use playback range?
            if sc.onionsk_fr_sc:
                self.fs = context.scene.frame_start
                self.fe = context.scene.frame_end
            if sc.onionsk_action_range:
                all_keys = self.os_methos_keyframe(obj, objp, curframe, dont_create=True)
                self.fs = all_keys[2][0]
                self.fe = all_keys[2][-1]
            # fix start to end
            if self.fe < self.fs:
                swap = self.fs
                self.fs = self.fe
                self.fe = swap
            self.Frames = self.evaluate_frames(
                self.objp, self.curframe, self.fs, self.fe, self.skip, 0, 0)
        if sc.onionsk_method == 'KEYFRAME':
            self.Frames = self.os_methos_keyframe(obj, objp, curframe)

    def make_frame(self, Frame):
        sc = bpy.context.scene.onion_skins_scene_props
        bpy.context.scene.frame_set(Frame)
        print("Onion Skin: Frame " + str(Frame))
        # CREATE TIMELINE'S MARKER AT THAT FRAME
        if sc.onionsk_tmarker is True:
            tmarkers = bpy.context.scene.timeline_markers
            tmarkers.new("os", frame=Frame)
        if sc.os_draw_technic == 'MESH':
            count = make_onionSkin_frame(self, self.objp, self.empty, self.curframe, Frame)
        if sc.os_draw_technic == 'GPU':
            count = make_gpu_frame(self.objp, self.curframe, Frame)
        self.Skins_count += count

    def finishing(self, context):
        sc = bpy.context.scene.onion_skins_scene_props
        params = bpy.context.window_manager.onionSkinsParams
        obj = self.obj
        objp = self.objp
        mode = self.mode
        curframe = self.curframe
        #////////////////////////////////////////////
        context.scene.frame_set(curframe)
        # update active Skins count
        objp.onionsk_Skins_count = self.Skins_count
        obj.select_set(True)
        context.view_layer.objects.active = obj
        if self.Frames:
            # Object custom property of using Onion Skins
            obj.is_onionsk = True
            objp.is_onionsk = True
            set_onion_colors('BEFORE')
            set_onion_colors('AFTER')

            # CREATE MOTION PATH
            if sc.onionsk_mpath is True:
                if sc.onionsk_method == 'FRAME' or sc.onionsk_method == 'SCENE':
                    create_update_motion_path(
                        context, mode, obj, self.fs, self.fe, [], [])
                if sc.onionsk_method == 'KEYFRAME':
                    create_update_motion_path(
                        context, mode, obj, 0, 0, self.kfbefore, self.kfafter)

        bpy.data.objects.update()
        bpy.data.scenes.update()

        # Count all Onion Skins in scene exept Markers
        Skins = 0
        for o in context.scene.objects:
            try:
                if o.onionsk_Skins_count > 0:
                    Skins = Skins + o.onionsk_Skins_count
            except AttributeError:
                continue
        sc.onionsk_Skins_count = Skins
        #!!!!!!!!!!!!Return to Stored Conext Mode ('POSE' for example)!!!!!!!!
        bpy.ops.object.mode_set(mode=mode)

        #Switch in Front property for display mesh in viewport properly.
        #If u don't then newly created mesh goes on top of it regardless.
        # Returning value state
        if self.inFront_get_value is True:
            params.mesh_inFront = True
        else:
            params.mesh_inFront = False
        global CREATING
        CREATING = False
        if sc.view_range:
            view_range_frames(context.scene)

        if sc.os_draw_technic == 'GPU' and not sc.draw_gpu_toggle:
            sc.draw_gpu_toggle = True

        if not params.display_progress and self.empty:
            msg = "Mesh Onion Skins Updated"
            self.report({'INFO'}, msg)

        return {'FINISHED'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        Progress_Status.hide(self)

##############################################################################


class OS_OT_Remove_Skins(bpy.types.Operator):
    bl_label = 'Remove Skins'
    bl_idname = 'mos_op.remove_skins'
    bl_description = "Delete Mesh Onion Skins for the selected Object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = bpy.context.selected_objects[0]
        sc = bpy.context.scene.onion_skins_scene_props
        #Remove timeline_markers
        tmarkers = bpy.context.scene.timeline_markers
        imarkers = tmarkers.items()
        for m in imarkers:
            if (m[0] == 'os'):
                tmarkers.remove(tmarkers.get('os'))
        #!!!!!!!!!!!!!!SET TO CONTEXT OBJECT MODE !!!!!!!!!!!!!!!!!
        #Store current mode to return to it after complete operations
        mode = bpy.context.mode
        bpy.ops.object.mode_set(mode='OBJECT')
        #Remove Motion paths
        if (mode == 'POSE'):
            bpy.ops.object.mode_set(mode='POSE')
            bpy.ops.pose.paths_clear(only_selected=False)
            bpy.ops.object.mode_set(mode='OBJECT')
        else:
            if sc.onionsk_mpath is True:
                bpy.ops.object.paths_clear(only_selected=False)
        # REMOVE Skins ////////
        remove_skins(obj)
        objp = checkout_parent(obj)
        sc.draw_gpu_toggle = False
        global GPU_FRAMES
        if GPU_FRAMES.get(obj.name):
            GPU_FRAMES[objp.name].clear()

        bpy.data.objects.update()
        bpy.context.scene.objects.update()
        # bpy.context.view_layer.update()
        # bpy.data.screens.update()

        bpy.context.view_layer.objects.active = obj

        # count all skins in scene
        Skins = 0
        for o in bpy.context.scene.objects:
            try:
                if o.onionsk_Skins_count > 0:
                    Skins = Skins + o.onionsk_Skins_count
            except AttributeError:
                continue
        sc.onionsk_Skins_count = Skins

        #!!!!!!!!!!!!Return to Stored Conext Mode ('POSE' for example)!!!!!!!!
        bpy.ops.object.mode_set(mode=mode)

        # msg = "Mesh Onion Skins Removed from Object"
        # self.report({'INFO'}, msg)

        return {'FINISHED'}

###############################################


class OS_OT_Add_Marker(bpy.types.Operator):
    bl_label = 'Add Marker'
    bl_idname = 'mos_op.add_marker'
    bl_description = "Add a marker skin at the current frame"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        sc = bpy.context.scene.onion_skins_scene_props
        params = bpy.context.window_manager.onionSkinsParams
        obj = bpy.context.selected_objects[0]
        # Check to see if object is a parent or a child
        objp = checkout_parent(obj)
        tmarkers = bpy.context.scene.timeline_markers
        curframe = bpy.context.scene.frame_current
        # start at current frame
        if sc.onionsk_tmarker is True:
            tmarkers.new("osm", frame=curframe)

        if sc.os_draw_technic == 'GPU':
            global GPU_MARKERS
            if not GPU_MARKERS.get(objp.name):
                GPU_MARKERS[objp.name] = {}
            count = make_gpu_frame(objp, curframe, curframe, skin_type='MARKER')
            sc.onionsk_Markers_count += count
            obj.is_os_marker = 1
            objp.is_os_marker = 1
            if not sc.draw_gpu_toggle:
                sc.draw_gpu_toggle = True
            msg = "Mesh Onion Marker Added"
            self.report({'INFO'}, msg)

            return {'FINISHED'}
        #Switch in Front property for display mesh in viewport properly.
        #If u don't then newly created mesh goes on top of it regardless.
        # It will be returned to previouse state at the end of operation.
        inFront_get_value = params.mesh_inFront
        params.mesh_inFront = False

        mode = bpy.context.mode
        bpy.ops.object.mode_set(mode='OBJECT')

        if sc.os_draw_technic == 'MESH':
            # Initially Create Collectiont for skins to be stored in
            init_os_collection()
            # Setup an 'empty' to use as a parent for Markers
            mark_skins_empty = create_skins_empty(objp, 'MARKER')
            if not mark_skins_empty:
                msg = "Mesh Onion Skins collection or parent Empty is hidden, make sure it is visible in View Layer"
                self.report({'ERROR'}, msg)
                count = 0
        # Setup the Colored MATERIALS for Skins
        create_skins_materials()
        obj.select_set(False)

        # CREATE MARKER SKIN
        if mark_skins_empty and sc.os_draw_technic == 'MESH':
            count = make_onionSkin_frame(self, objp, mark_skins_empty, curframe, curframe, 'MARKER')
        elif sc.os_draw_technic == 'GPU':
            count = make_onionSkin_frame(self, objp, mark_skins_empty, curframe, curframe, 'MARKER')
        # Update Marker Skins count
        if count:
            sc.onionsk_Markers_count += count
            obj.is_os_marker = 1
            objp.is_os_marker = 1
        # Make the Original Selected Mesh/Armature Active again
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        set_onion_colors('MARKER')

        bpy.data.objects.update()
        bpy.data.scenes.update()

        bpy.ops.object.mode_set(mode=mode)
        #Switch in Front property for display mesh in viewport properly.
        #If u don't then newly created mesh goes on top of it regardless.
        # Returning value state
        if inFront_get_value is True:
            params.mesh_inFront = True
        else:
            params.mesh_inFront = False
        if mark_skins_empty:
            msg = "Mesh Onion Marker Added"
            self.report({'INFO'}, msg)

        return {'FINISHED'}

##############################################################################


class OS_OT_Remove_Marker(bpy.types.Operator):
    bl_label = 'Remove Markers'
    bl_idname = 'mos_op.remove_marker'
    bl_description = "Remove Markers from the selected object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        obj = bpy.context.selected_objects[0]

        # Remove Timeline's markers
        tmarkers = bpy.context.scene.timeline_markers
        for m in tmarkers:
            if m.name == 'osm':
                tmarkers.remove(m)

        # Remove Markers ///////
        remove_skins(obj, skin_type='MARKER')
        sc = bpy.context.scene.onion_skins_scene_props
        if sc.draw_gpu_toggle and not obj.is_onionsk:
            sc.draw_gpu_toggle = False
        objp = checkout_parent(obj)
        global GPU_MARKERS
        if GPU_MARKERS.get(objp.name):
            for m in GPU_MARKERS[objp.name]:
                sc.onionsk_Markers_count -= 1
            GPU_MARKERS[objp.name].clear()
        if sc.onionsk_Markers_count < 0:
            sc.onionsk_Markers_count = 0

        bpy.data.objects.update()
        bpy.data.scenes.update()

        msg = "Mesh Onion Markers Removed"
        self.report({'INFO'}, msg)

        return {'FINISHED'}


class OS_OT_Update_Motion_Path(bpy.types.Operator):
    bl_label = 'Update Motion Path'
    bl_idname = 'mos_op.update_motion_path'
    bl_description = "Update motion path for the selected object"

    def execute(self, context):
        update_mpath(self, context)
        return {'FINISHED'}


class OS_OT_Clear_Motion_Path(bpy.types.Operator):
    bl_label = 'Clear Motion Path'
    bl_idname = 'mos_op.clear_motion_path'
    bl_description = "Clear motion path for the selected object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        remove_motion_paths()
        return {'FINISHED'}


def get_ao_collections(context):
    sc = bpy.context.scene.onion_skins_scene_props
    active_obj = context.active_object
    coll_scene = context.scene.collection
    coll_parents = parent_lookup(coll_scene)
    collection_list = []
    for c in active_obj.users_collection:
        if c.name == "Master Collection":
            continue
        collection_list.append(c.name)
        parent_colls = coll_parents.get(c.name)
        if parent_colls and sc.show_parent_users_collection:
            for pc in parent_colls:
                if pc == "Master Collection":
                    continue
                collection_list.append(pc)
    collection_list = list(set(collection_list))
    collection_list.sort()
    if not collection_list:
        return [('|@None@|', '', "")]
    return [(c, c, "") for c in collection_list]


def active_object_collections(self, context):
    return get_ao_collections(context)


def get_collection_objects(coll_name):
    if not coll_name or coll_name == '|@None@|':
        return []
    objects = bpy.data.collections[coll_name].objects
    checked_objects = []
    for o in objects:
        if o.type != 'MESH':
            continue
        try:
            checked_objects.append(bpy.context.view_layer.objects[o.name])
        except KeyError:
            continue
    return checked_objects


def check_uncheck_all_object_collection_items(flag="uncheck"):
    try:
        object_data_list = bpy.context.window_manager.os_childrens_collection
    except AttributeError:
        return None
    for item in object_data_list:
        if flag == "uncheck":
            item.flag = False
        else:
            item.flag = True


def get_object_settings_collection(obj):
    sc = bpy.context.scene.onion_skins_scene_props
    scene_objs_settings = bpy.context.scene.os_object_list_settings
    for ob_s in scene_objs_settings:
        if ob_s.name == obj.name and ob_s.list_type == sc.selection_sets:
            return [ob_s.show_parent_coll, ob_s.collection]


def get_object_settings_list(obj):
    params = bpy.context.window_manager.onionSkinsParams
    sc = bpy.context.scene.onion_skins_scene_props
    scene_objs_settings = bpy.context.scene.os_object_list_settings
    os_list = []
    for ob_s in scene_objs_settings:
        if ob_s.name == obj.name and ob_s.list_type == sc.selection_sets and \
                ob_s.collection == params.active_obj_users_collection:
            os_list = list(ob_s.settings.split(SEPARATOR))
            os_list = [(list(ol.split(', '))) for ol in os_list]
            os_list.pop(-1)
            break
    return os_list


def object_settings_remove(obj):
    scene_objs_settings = bpy.context.scene.os_object_list_settings
    for i, ob_s in enumerate(scene_objs_settings):
        if ob_s.name == obj.name:
            scene_objs_settings.remove(i)


os_obj_switching = False


def create_data_list(object_data_list, item_list, list_type='new'):
    global OS_Selected_Object_Sets
    global os_obj_switching
    os_obj_switching = True
    obj_list = []
    for il in item_list:
        item = object_data_list.add()
        if list_type == 'new':
            item.name = il.name
            item.flag = True
            obj_list.append((il.name, True))
        if list_type == 'settings':
            item.name = il[0]
            if il[1] == 'True':
                item.flag = True
            else:
                item.flag = False
    if list_type == 'new':
        selected_os_set = get_selected_os_set()
        obj = checkout_parent(bpy.context.active_object)
        OS_Selected_Object_Sets[selected_os_set] = obj_list
    os_obj_switching = False


def get_selected_os_set():
    params = bpy.context.window_manager.onionSkinsParams
    sc = bpy.context.scene.onion_skins_scene_props
    obj = checkout_parent(bpy.context.active_object)
    if sc.selection_sets == "COLLECTION":
        return obj.name + '|<@>|' + params.active_obj_users_collection
    if sc.selection_sets == "PARENT":
        return obj.name + '|<@>|' + '{_PARENT_}'


def get_selected_os_set_childrens():
    params = bpy.context.window_manager.onionSkinsParams
    sc = bpy.context.scene.onion_skins_scene_props
    if sc.selection_sets == "COLLECTION":
        return get_collection_objects(params.active_obj_users_collection)
    if sc.selection_sets == "PARENT":
        obj = checkout_parent(bpy.context.active_object)
        return [ob for ob in childrens_lookup(obj) if ob.type == 'MESH']


def update_active_obj_collection(self, context):
    params = bpy.context.window_manager.onionSkinsParams
    global OS_Selected_Object_Collection
    OS_Selected_Object_Collection[bpy.context.active_object.name] = params.active_obj_users_collection


def get_stored_collection():
    global OS_Selected_Object_Collection
    try:
        coll = OS_Selected_Object_Collection[bpy.context.active_object.name]
    except KeyError:
        try:
            coll = get_ao_collections(bpy.context)[0][0]
        except IndexError:
            return None
    return coll


def set_object_data_collection_items():
    params = bpy.context.window_manager.onionSkinsParams
    sc = bpy.context.scene.onion_skins_scene_props
    try:
        object_data_list = bpy.context.window_manager.os_childrens_collection
    except AttributeError:
        return None
    selected_os_set = get_selected_os_set()
    global OS_Selected_Object_Sets

    if bpy.context.window_manager.active_os_set != selected_os_set:
        if sc.selection_sets == "COLLECTION":
            try:
                params.active_obj_users_collection = get_stored_collection()
            except TypeError:
                pass
        item_list = []
        for item in object_data_list:
            item_list.append((item.name, item.flag))
        if item_list:
            OS_Selected_Object_Sets[bpy.context.window_manager.active_os_set] = item_list
        object_data_list.clear()
        bpy.context.window_manager.active_os_set = selected_os_set
        update_object_data_collection_items()

    if len(object_data_list) <= 0:
        obj = checkout_parent(bpy.context.active_object)
        os_list = get_object_settings_list(obj)
        if os_list:
            create_data_list(object_data_list, os_list, list_type='settings')
            return None

        childrens = get_selected_os_set_childrens()
        if childrens:
            create_data_list(object_data_list, childrens, list_type='new')


def update_object_data_collection_items():
    try:
        object_data_list = bpy.context.window_manager.os_childrens_collection
    except AttributeError:
        return None
    sc = bpy.context.scene.onion_skins_scene_props
    selected_os_set = get_selected_os_set()
    obj = checkout_parent(bpy.context.active_object)
    global OS_Selected_Object_Sets
    try:
        item_list = OS_Selected_Object_Sets[selected_os_set]
        list_type = "stored"
    except (KeyError, NameError) as e:
        item_list = get_object_settings_list(obj)
        list_type = "settings"
    object_data_list.clear()
    childrens = get_selected_os_set_childrens()
    global os_obj_switching
    if item_list:
        os_obj_switching = True
        for ob in childrens:
            item = object_data_list.add()
            found = False
            for i in item_list:
                if ob.name != i[0]:
                    continue
                item.name = ob.name
                if list_type == "settings":
                    if i[1] == 'True':
                        item.flag = True
                    else:
                        item.flag = False
                else:
                    item.flag = i[1]
                found = True
                break
            if not found:
                item.name = ob.name
                item.flag = True
    else:
        create_data_list(object_data_list, childrens, list_type='new')
    os_obj_switching = False


def highlight_active_object_list(obj, flag=True):
    if flag:
        obj.show_name = True
        obj.show_wire = True
        obj.show_bounds = True
        obj.display_bounds_type = 'BOX'
    else:
        obj.show_name = False
        obj.show_wire = False
        obj.show_bounds = False


def get_active_index_obj(context):
    wm = context.window_manager
    index = wm.active_os_object_list
    try:
        return bpy.data.objects[wm.os_childrens_collection[index].name]
    except (KeyError, IndexError) as e:
        return False


def update_highligh_obj_list(self, context):
    params = bpy.context.window_manager.onionSkinsParams
    obj = get_active_index_obj(context)
    if params.highlight_active_os_object_list and obj:
        highlight_active_object_list(obj, flag=True)
        params.active_obj_index_list_name = obj.name
    if not params.highlight_active_os_object_list and obj:
        highlight_active_object_list(obj, flag=False)


def update_selection_set(self, context):
    params = bpy.context.window_manager.onionSkinsParams
    if not params.highlight_active_os_object_list:
        return None
    try:
        prev_obj = bpy.data.objects[params.active_obj_index_list_name]
    except KeyError:
        prev_obj = False
    if prev_obj:
        highlight_active_object_list(prev_obj, flag=False)


def update_active_index_obj_name(self, context):
    params = bpy.context.window_manager.onionSkinsParams
    obj = get_active_index_obj(context)
    if params.active_obj_index_list_name == obj.name:
        return None
    if params.highlight_active_os_object_list and obj:
        highlight_active_object_list(obj, flag=True)
        try:
            prev_obj = bpy.data.objects[params.active_obj_index_list_name]
        except KeyError:
            prev_obj = False
        if prev_obj:
            highlight_active_object_list(prev_obj, flag=False)
    params.active_obj_index_list_name = obj.name


def rename_listed_skin_object(self, context):
    global os_obj_switching
    if os_obj_switching:
        return None
    params = bpy.context.window_manager.onionSkinsParams
    wm = context.window_manager
    index = wm.active_os_object_list
    try:
        obj_name = wm.os_childrens_collection[index].name
    except IndexError:
        return None
    try:
        bpy.data.objects[params.active_obj_index_list_name].name = obj_name
        params.active_obj_index_list_name = obj_name
    except KeyError:
        return None


class Object_Childrens_Collection(bpy.types.PropertyGroup):
    name: StringProperty(name="Skin Object", update=rename_listed_skin_object)
    flag: BoolProperty(name="Flag", default=True)


class OBJECT_list_settings(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="object name")
    settings: bpy.props.StringProperty(name="object list settings")
    list_type: bpy.props.StringProperty(name="list type")
    show_parent_coll: BoolProperty(name="show parent collection", default=False)
    collection: bpy.props.StringProperty(name="collection")


class WM_OT_list_uncheck_all(bpy.types.Operator):
    bl_label = 'Uncheck All'
    bl_idname = 'wm.os_uncheck_all_children_list'
    bl_description = "Uncheck all in the childrens list"

    def execute(self, context):
        check_uncheck_all_object_collection_items(flag="uncheck")
        return {'FINISHED'}


class WM_OT_list_check_all(bpy.types.Operator):
    bl_label = 'Check All'
    bl_idname = 'wm.os_check_all_children_list'
    bl_description = "Check all in the childrens list"
    # bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        check_uncheck_all_object_collection_items(flag="check")
        return {'FINISHED'}


class WM_OT_list_save_settings(bpy.types.Operator):
    bl_label = 'Save List Settings'
    bl_idname = 'wm.os_save_list_settings'
    bl_description = "Save settings of the childrens list for the current object"

    def execute(self, context):
        save_os_list_settings()
        return {'FINISHED'}


class WM_OT_list_load_settings(bpy.types.Operator):
    bl_label = 'Load List Settings'
    bl_idname = 'wm.os_load_list_settings'
    bl_description = "Load settings of the childrens list for the current object"

    def execute(self, context):
        load_os_list_settings()
        return {'FINISHED'}


class WM_OT_update_childrens_list(bpy.types.Operator):
    bl_label = 'Update Childrens List'
    bl_idname = 'wm.os_update_childrens_list'
    bl_description = "Update the childrens list of the active object"

    def execute(self, context):
        update_object_data_collection_items()
        return {'FINISHED'}


class WM_OT_object_list_settings_remove(bpy.types.Operator):
    bl_label = 'Remove List Settings'
    bl_idname = 'wm.os_list_settings_remove'
    bl_description = "Remove list settings of the active object"

    def execute(self, context):
        obj = checkout_parent(bpy.context.active_object)
        object_settings_remove(obj)
        self.report({'INFO'}, "List settings for '" + obj.name + "' has been removed")
        return {'FINISHED'}


class OnionSkins_Scene_Props(bpy.types.PropertyGroup):
    ob = bpy.types.Object
    ob.is_onionsk = bpy.props.BoolProperty(
        attr="is_onionsk",
        name='is_onionsk',
        description='Is object using Mesh Onion Skins',
        default=False)

    ob.is_os_marker = bpy.props.BoolProperty(
        attr="is_os_marker",
        name='is_os_marker',
        description='Is object using Mesh Onion Marker',
        default=False)

    ob.onionsk_Skins_count = bpy.props.IntProperty(
        attr="onionsk_Skins_count",
        name="onionsk_Skins_count",
        description='Active Onion Skins count in object',
        min=0, soft_min=0, max=10000, soft_max=10000, default=0)

    mat_color_bf: FloatVectorProperty(
        name="Before",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(0.1, 0.1, 1, 0.5),
        update=update_color_bf
    )
    mat_color_af: FloatVectorProperty(
        name="After",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(1, 0.1, 0.1, 0.5),
        update=update_color_af
    )
    mat_color_m: FloatVectorProperty(
        name="Marker",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(0, 0, 0, 0.5),
        update=update_color_m
    )

    fade_to_alpha: BoolProperty(
        name="Fade to Alpha",
        description="Fade onion skins to the edges of the frame range",
        default=True, update=update_fade_alpha)

    fade_to_value: FloatProperty(
        attr="fade_value",
        name="Fade value",
        description='Fade to Alpha color value',
        step=5,
        min=0.0, soft_min=0, max=1, soft_max=1, default=0.10,
        update=update_fade_alpha)

    color_alpha: BoolProperty(
        name="Alpha",
        description="Color alpha",
        default=True, update=update_color_alpha)

    color_alpha_value: FloatProperty(
        attr="color_alpha_value",
        name="Alpha",
        description='Color alpha value',
        step=5,
        min=0.0, soft_min=0, max=1, soft_max=1, default=0.5,
        update=update_color_alpha)

    onionsk_Markers_count: IntProperty(
        attr="onionsk_Markers_count",
        name='onionsk_Markers_count',
        description='Active Markers count in scene',
        min=0, soft_min=0, max=10000, soft_max=10000, default=0)

    onionsk_Skins_count: IntProperty(
        attr="onionsk_Skins_count",
        name="onionsk_Skins_count",
        description='Active Skins Count in Scene',
        min=0, soft_min=0, max=10000, soft_max=10000, default=0)

    onionsk_wire: BoolProperty(
        attr="onionsk_wire",
        name='onionsk_wire',
        description='Skin Mesh: Use Wireframe',
        default=False,
        update=update_os_prop_toggle_wire)

    show_in_render: BoolProperty(
        name="In Renders",
        description="Show in renders",
        default=True,
        update=update_os_prop_toggle_in_renders)

    os_selectable: BoolProperty(
        name='Selectable',
        description='Make Onion Skin object selectable',
        default=False,
        update=update_os_prop_toggle_selectable)

    onionsk_colors: BoolProperty(
        attr="onionsk_colors",
        name='onionsk_colors',
        description='Use colors (False = Use original Materials)',
        default=True, update=update_colors)

    gpu_flat_colors: BoolProperty(
        name='Flat Colors',
        description='Draw color filled silhouette only',
        default=False)

    gpu_colors_in_front: BoolProperty(
        name='In Front',
        description='Put skins in front of all objects',
        default=False)

    onionsk_fr_start: IntProperty(
        attr="onionsk_fr_start",
        name="onionsk_frames",
        description='Start at frame number',
        min=0, soft_min=0, max=10000, soft_max=10000, default=0)

    onionsk_fr_end: IntProperty(
        attr="onionsk_fr_end",
        name="onionsk_fr_end",
        description='End at frame number',
        min=0, soft_min=0, max=10000, soft_max=10000, default=100)

    onionsk_fr_before: IntProperty(
        attr="onionsk_fr_before",
        name="onionsk_fr_before",
        description='Frames before current',
        min=0, soft_min=0, max=10000, soft_max=10000, default=10)

    onionsk_fr_after: IntProperty(
        attr="onionsk_fr_after",
        name="onionsk_fr_after",
        description='Frames after current',
        min=0, soft_min=0, max=10000, soft_max=10000, default=10)

    onionsk_kfr_before: IntProperty(
        attr="onionsk_fr_before",
        name="onionsk_fr_before",
        description='Keys before current frame',
        min=0, soft_min=0, max=10000, soft_max=10000, default=1)

    onionsk_kfr_after: IntProperty(
        attr="onionsk_kfr_after",
        name="onionsk_kfr_after",
        description='Keys after current frame',
        min=0, soft_min=0, max=10000, soft_max=10000, default=1)

    view_before: IntProperty(
        attr="view_before",
        name="Backward",
        description='View frames before current frame',
        min=0, soft_min=0, max=10000, soft_max=10000, default=5,
        update=update_view_range)

    view_after: IntProperty(
        attr="view_after",
        name="Forward",
        description='View frames after current frame',
        min=0, soft_min=0, max=10000, soft_max=10000, default=5,
        update=update_view_range)

    onionsk_frame_step: IntProperty(
        attr="onionsk_frame_step",
        name="Frame Step",
        description='Frames to skip* (1 = draw every frame)\nFirst and last input frames is always included',
        min=1, soft_min=1, max=100, soft_max=100, default=5)

    onionsk_fr_sc: BoolProperty(
        attr="onionsk_fr_sc",
        name='Playback range',
        description='Use Start/End playback frames',
        default=False, update=update_in_range_playback)

    onionsk_action_range: BoolProperty(
        name='Action range',
        description='Use the current animation range',
        default=False, update=update_in_range_action)

    onionsk_skip: IntProperty(
        attr="onionsk_skip",
        name="Step",
        description='Frames to skip (1 = draw every frame)',
        min=1, soft_min=1, max=100, soft_max=100, default=1)

    os_draw_technic: EnumProperty(
        name="Draw Mode", items=[
            ('GPU', 'GPU',
             ''),
            ('MESH', 'Mesh',
             '')],
        description='Set draw mode', default='GPU',
        update=update_os_draw_technic)

    onionsk_method: EnumProperty(
        name="Draw Frame Methods", items=[
            ('FRAME', 'Around Frame',
             "Set skinned frames interval around current frame position"),
            ('KEYFRAME', 'Keyframes',
             "Draw skins at nearest keyframes located around\
              current frame position"),
            ('SCENE', 'In Range', 'Set start and end farmes\
              as a timeline interval')],
        description='Set where to draw method', default='SCENE')

    view_range: BoolProperty(
        attr="view_range",
        name='View Range',
        description='Use the view range to show onion skins at a specific frame range around the current frame position and hide others',
        default=False, update=update_view_range)

    use_all_keyframes: BoolProperty(
        name='All Keyframes',
        description='Use all keyframes of the current action to create onion skin at each of them',
        default=False)

    view_range_frame_type: EnumProperty(
        name="View Frame Type", items=[
            ('KEYFRAME', 'Keyframe',
             "Use the timeline keyframes for view range"),
            ('FRAME', 'Frame',
             "Use the timeline frames for view range")],
        description='Set type of frames for view range', default='KEYFRAME')

    onionsk_tmarker: BoolProperty(
        attr="onionsk_tmarker",
        name='onionsk_tmarker',
        description='Create time markers at frames',
        default=True, update=update_tmarker)

    onionsk_mpath: BoolProperty(
        attr="onionsk_mpath",
        name='onionsk_mpath',
        description='Show motion path of animated object',
        default=False, update=update_mpath)

    selection_sets: EnumProperty(
        name="Sets",
        items=[
            ('PARENT', 'Parent',
             "Object childrens list"),
            ('COLLECTION', 'Collection',
             "Collection objects list")],
        description='Set List Type',
        default='PARENT',
        update=update_selection_set)

    show_parent_users_collection: BoolProperty(
        name='Show Parent Collections',
        description='Show parent collections of the collection that contains the selected object',
        default=False)

    hide_os_before: BoolProperty(
        name="Hide Before",
        description="Hide before frames",
        default=True,
        update=hide_before_frames)
    hide_os_after: BoolProperty(
        name="Hide After",
        description="Hide after frames",
        default=True,
        update=hide_after_frames)
    hide_os_marker: BoolProperty(
        name="Hide Markers",
        description="Hide marker frames",
        default=True,
        update=hide_marker_frames)
    hide_os_all: BoolProperty(
        name="Hide All",
        description="Hide all frames",
        default=True,
        update=hide_all_frames)

    filter_keyframes: BoolProperty(
        name="Filter Keyframes",
        description="Include or exclude keyframe types",
        default=False)

    filter_active_bone: BoolProperty(
        name="Active Bone",
        description="Filter by keyframes of active bone only",
        default=False)

    key_type_keyframe: BoolProperty(
        name="Keyframe",
        description="Include or exclude keyframe types",
        default=True)
    key_type_breakdown: BoolProperty(
        name="Breakdown",
        description="Include or exclude keyframe types",
        default=True)
    key_type_movinghold: BoolProperty(
        name="Moving Hold",
        description="Include or exclude keyframe types",
        default=True)
    key_type_extreme: BoolProperty(
        name="Extreme",
        description="Include or exclude keyframe types",
        default=True)
    key_type_jitter: BoolProperty(
        name="Jitter",
        description="Include or exclude keyframe types",
        default=True)

    gpu_mask_oskins: BoolProperty(
        name="Mask Skins",
        description="Use depth mask of shader color for onion skin frames",
        default=False)
    gpu_mask_markers: BoolProperty(
        name="Mask Markers",
        description="Use depth mask of shader color for marker frames",
        default=False)

    def update_draw_gpu_toggle(self, context):
        if self.draw_gpu_toggle:
            bpy.ops.mos_op.gpu_draw_skins('INVOKE_DEFAULT')

    draw_gpu_toggle: BoolProperty(
        name="Draw Frames",
        description="Show onion skin frames in the 3D Viewport",
        default=False, update=update_draw_gpu_toggle)


def get_os_marker_frame_nums(self, context):
    sc = bpy.context.scene.onion_skins_scene_props
    objp = checkout_parent(context.active_object)
    if sc.os_draw_technic == 'GPU':
        if not GPU_MARKERS.get(objp.name):
            return []
        frame_nums = [float(s.split('|@|')[-1]) for s in GPU_MARKERS[objp.name]]
    else:
        treeM = get_empty_objs_tree(False, 'MARKER')
        if not treeM:
            return []
        frame_nums = [float(s.name.split('_')[-1]) for s in treeM.children]
    frame_nums = list(set(frame_nums))
    frame_nums.sort()
    enum = []
    for i, n in enumerate(frame_nums):
        enum.append(('Frame ' + str(int(n)), '    delete', '', i))
    return enum


SKIP_DELETE = False


def delete_mos_marker(self, context):
    global SKIP_DELETE
    if SKIP_DELETE:
        return None
    sc = bpy.context.scene.onion_skins_scene_props
    wm = bpy.context.window_manager
    if wm.mos_markers == '<UNKNOWN ENUM>':
        return None
    frame_number = wm.mos_markers.split(' ')[-1]
    obj = context.active_object
    objp = checkout_parent(obj)
    global GPU_MARKERS
    if sc.os_draw_technic == 'MESH':
        treeM = get_empty_objs_tree(False, 'MARKER')
        markers = treeM.children
        if not treeM:
            return None
        for s in markers:
            if int(float(s.name.split('_')[-1])) != int(float(frame_number)):
                continue
            mesh = s.data
            bpy.data.objects.remove(s, do_unlink=True)
            if bpy.data.meshes[mesh.name].users == 0:
                bpy.data.meshes.remove(mesh)
            sc.onionsk_Markers_count = sc.onionsk_Markers_count - 1
            tm = bpy.context.scene.timeline_markers
            for m in tm:
                if m.frame == int(frame_number) and m.name == 'osm':
                    tm.remove(m)
    elif GPU_MARKERS.get(objp.name):
        markers = []
        for gm in GPU_MARKERS[objp.name]:
            if int(float(gm.split('|@|')[-1])) != int(float(frame_number)):
                continue
            markers.append(gm)
            tm = bpy.context.scene.timeline_markers
            for m in tm:
                if m.frame == int(frame_number) and m.name == 'osm':
                    tm.remove(m)
        for m in markers:
            GPU_MARKERS[objp.name].pop(m)
            sc.onionsk_Markers_count -= 1
        markers = GPU_MARKERS[objp.name]
    SKIP_DELETE = True
    if markers:
        wm['mos_markers'] = 0
    SKIP_DELETE = False

    if not markers:
        if sc.os_draw_technic == 'MESH':
            bpy.data.objects.remove(treeM, do_unlink=True)
        obj.is_os_marker = 0
        objp.is_os_marker = 0
        sc = bpy.context.scene.onion_skins_scene_props
        if sc.draw_gpu_toggle and not obj.is_onionsk:
            sc.draw_gpu_toggle = False


class OnionSkinsParams(bpy.types.PropertyGroup):

    onion_skins_init: BoolProperty(
        name="Initialize",
        default=False)

    mesh_inFront: BoolProperty(
        name="In Front",
        description='Make the object draw in front of others',
        default=False, update=mesh_show_inFront)

    mesh_wire: BoolProperty(
        name="Wireframe",
        description="Add the object's wireframe over solid drawing",
        default=False, update=mesh_show_wire)

    color_type: EnumProperty(
        name="Shading Color Type",
        items=[
            ('MATERIAL', 'Material',
             "Show material color"),
            ('OBJECT', 'Object',
             "Show object color"),
            ('TEXTURE', 'Texture',
             "Show texture")],
        description='Viewport: Solid Shading Color Type',
        default='MATERIAL', update=shading_color_type)

    active_obj_users_collection: EnumProperty(
        name="Collections",
        items=active_object_collections,
        update=update_active_obj_collection)

    active_obj_index_list_name: StringProperty(
        name="index list name")

    highlight_active_os_object_list: BoolProperty(
        name="Highlight Object",
        description="Show name, wireframe and bounding box for the selected object in the list to highlight it in the viewport",
        default=False,
        update=update_highligh_obj_list)

    bpy.types.WindowManager.mos_markers = EnumProperty(
        items=get_os_marker_frame_nums,
        update=delete_mos_marker
    )
    display_progress: BoolProperty(
        name="Display Progress",
        description="Show progress in the window UI while creating onion skins ( creating is slower if turned on )",
        default=False)


def update_pref_color_alpha(self, context):
    if not self.color_alpha:
        self.fade_to_alpha = False
    else:
        update_pref_color_alpha_value(self, context)


def update_pref_color_alpha_value(self, context):
    if self.color_alpha:
        self.color_bf[3] = self.color_alpha_value
        self.color_af[3] = self.color_alpha_value
        self.color_m[3] = self.color_alpha_value


class Onion_Skins_Preferences(AddonPreferences):
    bl_idname = __name__

    category: StringProperty(
        name="Tab Category",
        description="Choose a name for the category of the panel",
        default="Animation",
        update=update_panel
    )
    color_bf: FloatVectorProperty(
        name="Before",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(0.1, 0.1, 1, 0.5),
        # update=update_color_bf
    )
    color_af: FloatVectorProperty(
        name="After",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(1, 0.1, 0.1, 0.5),
        # update=update_color_af
    )
    color_m: FloatVectorProperty(
        name="Marker",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(0, 0, 0, 0.5),
        # update=update_color_m
    )

    display_progress: BoolProperty(
        name="Display Progress",
        description="Draw Mode: Mesh: Show progress in the window UI while creating onion skins ( creating is slower while turned on )",
        default=True)

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        col = row.column()
        col.label(text="Tab Category:")
        col.prop(self, "category", text="")
        box = col.box()
        box.label(text="Colors:")
        flow = box.grid_flow(row_major=True, columns=3, even_columns=True, even_rows=False, align=True)
        col = flow.column(align=True)
        col.label(text="Before")
        col.prop(self, 'color_bf', text='')  # , text="Before"
        col = flow.column(align=True)
        col.label(text="After")
        col.prop(self, 'color_af', text='')  # , text="After"
        col = flow.column(align=True)
        col.label(text="Marker")
        col.prop(self, 'color_m', text='')
        row = layout.row()
        row.prop(self, 'display_progress')


class WM_MT_List_Ops(Menu):
    bl_label = "List Operations"
    bl_idname = "WM_MT_List_ops_menu"

    def draw(self, context):
        layout = self.layout
        layout.operator("wm.os_save_list_settings", icon="FILE_TICK")
        layout.operator("wm.os_load_list_settings", icon="IMPORT")
        layout.separator()
        layout.operator("wm.os_list_settings_remove", icon='X')


class WM_MT_Marker_List_Popup(bpy.types.Operator):
    bl_label = 'Select Markers to Delete'
    bl_idname = 'mos_wm.delete_selected_markers'
    bl_description = "Delete the specific marker at frame number"

    def execute(self, context):
        return {'FINISHED'}

    def draw(self, context):
        wm = bpy.context.window_manager

        layout = self.layout
        row = layout.row(align=True)
        row.label(text="Delete Markers:")
        row = layout.row(align=True)
        col = row.column(align=True)
        for ident, name, blank, frame in get_os_marker_frame_nums(self, context):
            m = col.row()
            m.label(text=ident)
        col = row.column(align=True)
        col.alignment = 'EXPAND'
        col.emboss = 'NORMAL'
        col.scale_y = 1.1
        col.prop_tabs_enum(wm, 'mos_markers')

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=150)


def save_os_list_settings():
    try:
        object_data_list = bpy.context.window_manager.os_childrens_collection
    except AttributeError:
        return None
    if not bpy.context.active_object:
        return None
    params = bpy.context.window_manager.onionSkinsParams
    sc = bpy.context.scene.onion_skins_scene_props
    obj = checkout_parent(bpy.context.active_object)
    item_list = []
    for item in object_data_list:
        item_list.append((item.name, item.flag))
    OS_Selected_Object_Sets[bpy.context.window_manager.active_os_set] = item_list
    for ob_s in bpy.context.scene.os_object_list_settings:
        if ob_s.name == obj.name and ob_s.list_type == sc.selection_sets:
            ob_s.show_parent_coll = sc.show_parent_users_collection
            ob_s.collection = params.active_obj_users_collection
            ob_s.settings = list_to_str(item_list, SEPARATOR)
            return None
    scene_item = bpy.context.scene.os_object_list_settings.add()
    scene_item.name = obj.name
    scene_item.list_type = sc.selection_sets
    scene_item.show_parent_coll = sc.show_parent_users_collection
    scene_item.collection = params.active_obj_users_collection
    scene_item.settings = list_to_str(item_list, SEPARATOR)


def load_os_list_settings():
    params = bpy.context.window_manager.onionSkinsParams
    sc = bpy.context.scene.onion_skins_scene_props
    try:
        object_data_list = bpy.context.window_manager.os_childrens_collection
    except AttributeError:
        return None
    object_data_list.clear()
    obj = checkout_parent(bpy.context.active_object)
    if sc.selection_sets == "COLLECTION":
        try:
            sc.show_parent_users_collection = get_object_settings_collection(obj)[0]
            params.active_obj_users_collection = get_object_settings_collection(obj)[1]
        except TypeError:
            pass
    os_list = get_object_settings_list(obj)
    if os_list:
        create_data_list(object_data_list, os_list, list_type='settings')


def m_os_pre_save(dummy):
    save_os_list_settings()


def set_view_colors(s, s_type):
    sc = bpy.context.scene.onion_skins_scene_props
    if sc.onionsk_colors:
        m = get_base_material(s_type)
        if not m:
            create_skins_materials()
            m = get_base_material(s_type)
    else:
        m = bpy.data.materials[
            MAT_PREFIX + list_to_str(s.name.split('_')[1:-1], '_') + '_' + SUFFIX_own]
    s.data.materials[0] = m
    s.color = m.diffuse_color


def set_view_range_props(scene, s, view_range, s_type):
    sc = bpy.context.scene.onion_skins_scene_props
    for i in range(1, view_range + 1):
        if s_type == 'before':
            frame = scene.frame_current - i
        if s_type == 'after':
            frame = scene.frame_current + i
        if s.name.endswith('_' + str(frame)):
            if s.hide_viewport:
                s.hide_viewport = False
            set_view_colors(s, s_type)
            if sc.show_in_render:
                s.hide_render = False
            return True
    return False


def view_range_frames(scene):
    global CREATING
    if CREATING:
        return None
    sc = bpy.context.scene.onion_skins_scene_props
    if not sc.view_range:
        return None
    if sc.os_draw_technic == 'GPU':
        return None
    tree = get_empty_objs_tree()
    if not tree:
        return None
    sk_names_before = []
    sk_names_after = []
    for s in tree.children:
        if scene.frame_current - 1 >= scene.frame_current - sc.view_before and \
                sc.hide_os_before:
            if set_view_range_props(scene, s, sc.view_before, 'before'):
                sk_names_before.append(s.name)
                continue
        if scene.frame_current + 1 <= scene.frame_current + sc.view_after and \
                sc.hide_os_after:
            if set_view_range_props(scene, s, sc.view_after, 'after'):
                sk_names_after.append(s.name)
                continue
        if not s.hide_viewport:
            s.hide_viewport = True
        if not s.hide_render:
            s.hide_render = True
    if not sc.fade_to_alpha:
        return None
    if sc.hide_os_before:
        mat_color = get_prefix_material_color('before')
        fade_onion_colors(
            sk_names_before, 'before', mat_color, len(sk_names_before),
            view_range=True)
    if sc.hide_os_after:
        mat_color = get_prefix_material_color('after')
        fade_onion_colors(
            sk_names_after, 'after', mat_color, len(sk_names_after),
            view_range=True)


def m_os_post_frames_handler(scene):
    global RENDERING
    if RENDERING:
        return None
    view_range_frames(scene)


def m_os_pre_render_handler(scene):
    global RENDERING
    RENDERING = True
    if not scene.onion_skins_scene_props.view_range:
        return None
    if not scene.render.use_lock_interface and sc.os_draw_technic == 'MESH':
        scene.render.use_lock_interface = True
    view_range_frames(scene)


def m_os_post_render_handler(dummy):
    global RENDERING
    RENDERING = False


def m_os_cancel_render_handler(dummy):
    global RENDERING
    RENDERING = False


def m_os_on_file_load(scene):
    remove_handlers(bpy.context)
    global GPU_FRAMES
    global GPU_MARKERS
    GPU_FRAMES.clear()
    GPU_MARKERS.clear()


def m_os_post_dpgraph_update(scene):
    check_draw_gpu_toggle(scene)


classes = [
    # OS_PT_UI_Panel,
    # OS_PT_Frames_Panel,
    # OS_PT_Options_Panel,
    # OS_PT_Colors_Panel,
    # OS_PT_Selection_Panel,
    # OS_PT_View_Range_Panel,
    # OS_PT_FilterKeys_Panel,
    # OS_PT_Visibility_Panel,
    OS_OT_CreateUpdate_Skins,
    OS_OT_Remove_Skins,
    OS_OT_Add_Marker,
    OS_OT_Remove_Marker,
    OS_OT_Update_Motion_Path,
    OS_OT_Clear_Motion_Path,
    GPU_OT_Draw_Skins,
    Object_Childrens_Collection,
    OBJECT_UL_Childrens,
    OBJECT_list_settings,
    WM_OT_update_childrens_list,
    WM_OT_object_list_settings_remove,
    WM_OT_list_check_all,
    WM_OT_list_uncheck_all,
    WM_OT_list_save_settings,
    WM_OT_list_load_settings,
    WM_MT_List_Ops,
    WM_MT_Marker_List_Popup,
    OnionSkinsParams,
    OnionSkins_Scene_Props,
    Onion_Skins_Preferences,
]


def register():
    for panel in panels:
        bpy.utils.register_class(panel)

    for cls in classes:
        bpy.utils.register_class(cls)

    wm = bpy.types.WindowManager
    wm.onionSkinsParams = \
        PointerProperty(type=OnionSkinsParams)
    bpy.types.Scene.onion_skins_scene_props = \
        PointerProperty(type=OnionSkins_Scene_Props)
    wm.os_childrens_collection = \
        CollectionProperty(type=Object_Childrens_Collection)
    wm.active_os_object_list = IntProperty(
        name='Active children object in the list',
        min=0, soft_min=0, max=10000, soft_max=10000, default=0, update=update_active_index_obj_name)
    wm.active_os_set = StringProperty(
        name='Active Object')
    bpy.types.Scene.os_object_list_settings = bpy.props.CollectionProperty(type=OBJECT_list_settings)

    bpy.app.handlers.load_post.append(m_os_on_file_load)
    bpy.app.handlers.depsgraph_update_post.append(m_os_post_dpgraph_update)
    bpy.app.handlers.save_pre.append(m_os_pre_save)
    bpy.app.handlers.frame_change_post.append(m_os_post_frames_handler)
    bpy.app.handlers.render_pre.append(m_os_pre_render_handler)
    bpy.app.handlers.render_post.append(m_os_post_render_handler)
    bpy.app.handlers.render_cancel.append(m_os_cancel_render_handler)
    update_panel(None, bpy.context)


def unregister():
    remove_handlers(bpy.context)
    del bpy.types.WindowManager.onionSkinsParams
    del bpy.types.WindowManager.os_childrens_collection
    del bpy.types.WindowManager.active_os_object_list
    del bpy.types.WindowManager.active_os_set
    del bpy.types.Scene.onion_skins_scene_props
    del bpy.types.Scene.os_object_list_settings
    global OS_Selected_Object_Sets
    try:
        OS_Selected_Object_Sets.clear()
        del OS_Selected_Object_Sets
    except NameError:
        pass
    try:
        bpy.app.handlers.load_post.remove(m_os_on_file_load)
    except ValueError:
        pass
    try:
        bpy.app.handlers.depsgraph_update_post.remove(m_os_post_dpgraph_update)
        bpy.app.handlers.save_pre.remove(m_os_pre_save)
        bpy.app.handlers.frame_change_post.remove(m_os_post_frames_handler)
        bpy.app.handlers.render_pre.remove(m_os_pre_render_handler)
        bpy.app.handlers.render_post.remove(m_os_post_render_handler)
        bpy.app.handlers.render_cancel.remove(m_os_cancel_render_handler)
    except ValueError:
        pass

    for panel in panels:
        bpy.utils.unregister_class(panel)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
