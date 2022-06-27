
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
import os
import json
import time
import gpu
if bpy.app.version < (3, 0, 0):
    import bgl
import numpy as np
from bpy.app.handlers import persistent
from bpy.props import *
from bpy.types import Menu, Panel, AddonPreferences, Operator
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix

bl_info = {
    'name': "Mesh Onion Skins",
    'author': "TingJoyBits",
    'version': (1, 1, 3),
    'blender': (2, 80, 0),
    'location': "View3D > Animation > Mesh Onion Skins",
    'description': "Mesh Onion Skins for Blender Animations",
    'doc_url': "https://github.com/tingjoybits/Mesh_Onion_Skins",
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
    if obj.type == 'ARMATURE':
        return obj
    if obj.parent:
        return obj.parent
    return obj


def traverse_tree(t):
    yield t
    for child in t.children:
        yield from traverse_tree(child)


def parent_lookup(coll):
    parent_lookup = {}
    for coll in traverse_tree(coll):
        for c in coll.children.keys():
            if parent_lookup.get(c):
                parent_lookup[c].append(coll.name)
            else:
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
    children_list = [i.name for i in wm.os_childrens_collection]
    childrens = childrens_lookup(obj, list_type='name') + children_list
    childrens.append(obj.name)
    for c in childrens:
        ob = bpy.data.objects[c]
        if ob.type != 'MESH':
            continue
        if self.mesh_wire:
            if not ob.show_wire:
                ob.show_wire = True
        else:
            if ob.show_wire:
                ob.show_wire = False


def mesh_show_inFront(self, context):
    obj = context.active_object
    wm = context.window_manager
    children_list = [i.name for i in wm.os_childrens_collection]
    childrens = childrens_lookup(obj, list_type='name') + children_list
    childrens.append(obj.name)
    for c in childrens:
        ob = bpy.data.objects[c]
        if ob.type != 'MESH':
            continue
        if self.mesh_inFront:
            if not ob.show_in_front:
                ob.show_in_front = True
        else:
            if ob.show_in_front:
                ob.show_in_front = False


def shading_color_type(self, context):
    shading = bpy.context.space_data.shading
    if self.color_type == 'MATERIAL' and shading.color_type != 'MATERIAL':
        shading.color_type = 'MATERIAL'
    if self.color_type == 'TEXTURE' and shading.color_type != 'TEXTURE':
        shading.color_type = 'TEXTURE'
    if self.color_type == 'OBJECT' and shading.color_type != 'OBJECT':
        shading.color_type = 'OBJECT'
    sc = bpy.context.scene.onion_skins_scene_props
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
    if self.view_range:
        view_range_frames(context.scene)


def update_color_af(self, context):
    tree = get_empty_objs_tree()
    if not tree:
        set_base_material_colors('after')
        return None
    set_onion_colors('AFTER')
    if self.view_range:
        view_range_frames(context.scene)


def update_color_m(self, context):
    tree = get_empty_objs_tree(False, 'MARKER')
    if not tree:
        set_base_material_colors('marker')
        return None
    set_onion_colors('MARKER')


def update_colors(self, context):
    set_onion_colors('BEFORE', fade=True)
    set_onion_colors('AFTER', fade=True)
    set_onion_colors('MARKER')
    if self.fade_to_alpha is False:
        update_fade_alpha(self, context)
    if self.view_range:
        view_range_frames(context.scene)


def update_color_alpha(self, context):
    if self.color_alpha:
        self.mat_color_bf[3] = self.color_alpha_value
        self.mat_color_af[3] = self.color_alpha_value
        self.mat_color_m[3] = self.color_alpha_value
    else:
        self.mat_color_bf[3] = 1.0
        self.mat_color_af[3] = 1.0
        self.mat_color_m[3] = 1.0
        if self.fade_to_alpha:
            self.fade_to_alpha = False
    set_onion_colors('BEFORE')
    set_onion_colors('AFTER')
    set_onion_colors('MARKER')
    if self.view_range:
        view_range_frames(context.scene)


def update_fade_alpha(self, context):
    tree = get_empty_objs_tree()
    if not tree:
        return None
    if self.fade_to_alpha is False:
        for s in tree.children:
            try:
                if self.onionsk_colors:
                    if s.name.split('_')[0] == 'before':
                        s.data.materials[0] = bpy.data.materials[MAT_PREFIX + SUFFIX_before]
                    if s.name.split('_')[0] == 'after':
                        s.data.materials[0] = bpy.data.materials[MAT_PREFIX + SUFFIX_after]
                else:
                    s.data.materials[0] = bpy.data.materials[
                        MAT_PREFIX + list_to_str(s.name.split('_')[1:-1], '_') + '_' + SUFFIX_own]
            except KeyError:
                pass
    if self.color_alpha is False and self.fade_to_alpha is True:
        self.color_alpha = True
    set_onion_colors('BEFORE')
    set_onion_colors('AFTER')
    if self.view_range:
        view_range_frames(context.scene)


def update_os_prop_toggle(self, context, prop):
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
            if self.onionsk_wire:
                s.show_wire = True
            else:
                s.show_wire = False
        if prop == 'in_renders':
            if self.show_in_render:
                s.hide_render = False
            else:
                s.hide_render = True
        if prop == 'selectable':
            if self.os_selectable:
                s.hide_select = False
            else:
                s.hide_select = True
    if self.view_range and prop == 'in_renders':
        view_range_frames(context.scene)


def update_os_prop_toggle_wire(self, context):
    update_os_prop_toggle(self, context, 'wire')


def update_os_prop_toggle_in_renders(self, context):
    update_os_prop_toggle(self, context, 'in_renders')


def update_os_prop_toggle_selectable(self, context):
    update_os_prop_toggle(self, context, 'selectable')


def update_view_range(self, context):
    if not handler_check(bpy.app.handlers.frame_change_post, "m_os_post_frames_handler"):
        bpy.app.handlers.frame_change_post.append(m_os_post_frames_handler)
    if self.view_range:
        view_range_frames(context.scene)
        return None
    tree = get_empty_objs_tree()
    if not tree:
        return None
    for s in tree.children:
        if self.show_in_render:
            s.hide_render = True
        if s.name.split('_')[0] == 'before':
            if not self.hide_os_before:
                s.hide_viewport = True
            else:
                s.hide_viewport = False
        if s.name.split('_')[0] == 'after':
            if not self.hide_os_after:
                s.hide_viewport = True
            else:
                s.hide_viewport = False
    if self.fade_to_alpha:
        self.fade_to_alpha = True
    else:
        self.fade_to_alpha = False


def update_view_range_frame_type(self, context):
    if not self.os_draw_mode == 'MESH':
        return None
    view_range_frames(context.scene)


def update_auto_update_view(self, context):
    if self.auto_update_view_range and self.auto_update_single_frame:
        self.auto_update_single_frame = False


def update_auto_update_single(self, context):
    if self.auto_update_single_frame and self.auto_update_view_range:
        self.auto_update_view_range = False


def NoKeysError(self, context):
    msg = "Mesh Onion Skins: Keyframes didn't found. Use Edit strip mode of the action if animation data is not empty."
    print(msg)
    self.layout.label(text=msg)


def update_mpath(self, context):
    params = bpy.context.window_manager.onionSkinsParams
    if not params.onion_skins_init:
        return None
    sc = bpy.context.scene.onion_skins_scene_props
    if sc.onionsk_mpath is False:
        remove_motion_paths(context, context.mode, only_selected=False)
        return None
    wm = context.window_manager
    mode = context.mode
    obj = context.active_object
    global CREATING
    CREATING = True
    OSkins = Onion_Skins(obj=obj)
    if sc.onionsk_method == 'FRAME':
        fs, fe = OSkins.os_method_frame(dont_create=True)
        create_update_motion_path(context, mode, obj, fs, fe, [], [])
    if sc.onionsk_method == 'SCENE':
        fs, fe = OSkins.os_method_range(context, dont_create=True)
        if fs is False and fe is False:
            CREATING = False
            if not hasattr(self, 'onionsk_mpath'):
                wm.popup_menu(NoKeysError, title="Error", icon="INFO")
            return None
        create_update_motion_path(context, mode, obj, fs, fe, [], [])
    if sc.onionsk_method == 'KEYFRAME':
        kfb_kfa = OSkins.os_method_keyframe(dont_create=True)
        if not kfb_kfa:
            CREATING = False
            if not hasattr(self, 'onionsk_mpath'):
                wm.popup_menu(NoKeysError, title="Error", icon="INFO")
            return None
        create_update_motion_path(context, mode, obj, 0, 0, kfb_kfa[0], kfb_kfa[1])
    CREATING = False


def update_tmarker(self, context):
    sc = context.scene.onion_skins_scene_props
    if sc.onionsk_tmarker is False:
        remove_time_markers()
        return None
    if sc.os_draw_mode == 'GPU':
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
        tmarkers.new("os", frame=int(frame))


def update_os_draw_technic(self, context):
    sc = context.scene.onion_skins_scene_props
    if sc.onionsk_tmarker:
        remove_time_markers()
        update_tmarker(self, context)
    update_object_data_collection_items()


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
    if not obj:
        return False
    if hasattr(obj.animation_data, 'action'):
        return True
    elif obj.parent:
        if hasattr(obj.parent.animation_data, 'action'):
            return True
    return False


def apply_pref_settings():
    prefs = bpy.context.preferences.addons[__name__].preferences
    sc = bpy.context.scene.onion_skins_scene_props
    for pr in prefs.__annotations__:
        if pr == 'category' or pr == 'display_progress':
            continue
        exec("sc." + pr + " = prefs." + pr)


def handler_check(handler, function_name):
    if len(handler) <= 0:
        return False
    for i, h in enumerate(handler):
        func = str(handler[i]).split(' ')[1]
        if func == function_name:
            return True
    return False


def check_handlers():
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


def move_preset_file_after_install():
    module_path = os.path.dirname(__file__)
    presets_path = os.path.join(get_config_path(), "presets")
    file_name = 'All Keyframes View 2.json'
    preset_file_path = os.path.join(module_path, file_name)
    move_to_path = os.path.join(presets_path, file_name)
    if os.path.isfile(preset_file_path):
        import shutil
        if not os.path.isdir(presets_path):
            os.mkdir(presets_path, mode=0o777)
        shutil.move(preset_file_path, move_to_path)


def set_shading_color_type():
    if not hasattr(bpy.context.space_data, 'shading'):
        return None
    params = bpy.context.window_manager.onionSkinsParams
    shading = bpy.context.space_data.shading
    if shading.color_type != 'MATERIAL' and\
            shading.color_type != 'TEXTURE' and\
            shading.color_type != 'OBJECT':
        params.color_type = 'MATERIAL'
    else:
        params.color_type = shading.color_type


def OS_Initialization():
    params = bpy.context.window_manager.onionSkinsParams
    if params.onion_skins_init:
        return None
    if 'onion_skins_scene_props' not in bpy.context.scene or\
            not bpy.context.blend_data.filepath:
        apply_pref_settings()
    prefs = bpy.context.preferences.addons[__name__].preferences
    sc = bpy.context.scene.onion_skins_scene_props
    remove_handlers(bpy.context)
    global GPU_FRAMES
    global GPU_MARKERS
    GPU_FRAMES.clear()
    GPU_MARKERS.clear()

    check_handlers()

    if prefs.display_progress:
        params.display_progress = True

    set_shading_color_type()
    load_os_list_settings()
    item_ob = get_active_index_obj(bpy.context)
    if item_ob:
        params.active_obj_index_list_name = item_ob.name

    move_preset_file_after_install()
    params.onion_skins_init = True


def poll_check(context):
    if not context.active_object:
        return False
    if context.mode != 'OBJECT' and\
            context.mode != 'POSE' and\
            context.mode != 'SCULPT':
        return False
    if not hasattr(context.active_object, 'type'):
        return False
    if context.active_object.type == 'MESH' or\
            context.active_object.type == 'ARMATURE':
        return True
    return False


class OS_PT_UI_Panel(Panel):

    bl_label = "Mesh Onion Skins"
    bl_space_type = 'VIEW_3D'
    bl_region_type = "UI"
    bl_category = "Animation"

    def __init__(self):
        OS_Initialization()

    @classmethod
    def poll(self, context):
        return poll_check(context)

    def draw(self, context):
        layout = self.layout
        params = bpy.context.window_manager.onionSkinsParams
        obj = context.active_object
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
        row.prop(params, 'auto_update_skins_toggle', text='', icon='DISC')
        row.popover("POPOVER_PT_auto_update", text='', icon='DOWNARROW_HLT')
        row.separator()
        row.prop(sc, 'os_draw_mode', text='')
        row.separator()
        row.popover("POPOVER_PT_settings_presets", text='', icon='PRESET')
        row.operator('mos_op.show_pref_settings', text='', icon='PREFERENCES')
        row = layout.row(align=True)
        row.scale_y = 1.2
        if sc.onionsk_mpath:
            row.operator('mos_op.update_motion_path', text='', icon='IPO_ELASTIC')
        if sc.onionsk_mpath and mp.has_motion_paths:
            row.operator('mos_op.clear_motion_path', text='', icon='X')
        if not onionsk:
            row.operator('mos_op.make_skins', text='Create ', icon='ONIONSKIN_ON')
            if sc.os_draw_mode == 'MESH':
                row.prop(params, 'display_progress', text='', icon='TEMP')
            if (sc.onionsk_Markers_count > 0 and obj.is_os_marker) and\
                    sc.os_draw_mode == 'GPU':
                row.prop(sc, 'draw_gpu_toggle', text='', icon='RENDER_ANIMATION')
        else:
            row.operator('mos_op.make_skins', text='Update ', icon='ONIONSKIN_ON')
            if sc.os_draw_mode == 'GPU':
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

        if poll_check(context):
            if actions_check(context.active_object):
                return True
        return False

    def draw(self, context):
        obj = context.active_object
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

        if poll_check(context):
            if actions_check(context.active_object):
                return True
        return False

    def draw(self, context):
        layout = self.layout
        params = bpy.context.window_manager.onionSkinsParams
        obj = context.active_object
        sc = bpy.context.scene.onion_skins_scene_props
        actions = actions_check(obj)
        if not actions:
            return {'FINISHED'}
        box = layout.box()
        col = box.column(align=True)
        row = box.row()
        col.label(text="Onion Skins Settings:")
        if sc.os_draw_mode == 'MESH':
            row.prop(sc, "show_in_render")
            row.prop(sc, "os_selectable")
            row = box.row()
            row.prop(sc, "onionsk_colors", text="Colors")
            row.prop(sc, "onionsk_wire", text="Wireframe")
        elif sc.os_draw_mode == 'GPU':
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
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(self, context):
        if poll_check(context):
            return True
        return False

    def draw(self, context):
        layout = self.layout
        params = bpy.context.window_manager.onionSkinsParams
        obj = context.active_object
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
        if poll_check(context):
            set_object_data_collection_items()
            return True
        return False

    def draw(self, context):
        layout = self.layout
        params = bpy.context.window_manager.onionSkinsParams
        # obj = bpy.context.selected_objects[0]
        obj = context.active_object
        sc = bpy.context.scene.onion_skins_scene_props
        Skins = sc.onionsk_Skins_count
        onionsk = obj.is_onionsk
        actions = actions_check(obj)

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
            obj_child = len(get_selected_os_set_childrens())
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
        if poll_check(context):
            set_object_data_collection_items()
            return True
        return False

    def draw_header(self, context):
        sc = bpy.context.scene.onion_skins_scene_props
        layout = self.layout
        layout.prop(sc, 'view_range', text='')

    def draw(self, context):
        sc = bpy.context.scene.onion_skins_scene_props
        layout = self.layout
        row = layout.row(align=True)
        if sc.onionsk_method == 'KEYFRAME':
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
        if poll_check(context):
            obj = bpy.context.active_object
            if obj.is_onionsk or obj.is_os_marker:
                return True
        return False

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
        coll = bpy.data.collections.new(name=OS_collection_name)
        bpy.context.scene.collection.children.link(coll)
        empty = bpy.data.objects.new(OS_empty_name, None)
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
        e = bpy.data.objects.new(empty_name, None)
        e.select_set(False)
        # make the EMPTY a child of the main empty
        e.parent = bpy.data.objects[OS_empty_name]
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
        # m.use_fake_user = True
    try:
        m = bpy.data.materials[MAT_PREFIX + SUFFIX_after]
    except KeyError:
        bpy.data.materials.new(MAT_PREFIX + SUFFIX_after)
        m = bpy.data.materials[MAT_PREFIX + SUFFIX_after]
        format_os_material(m, sc.mat_color_af)
        # m.use_fake_user = True
    try:
        m = bpy.data.materials[MAT_PREFIX + SUFFIX_marker]
    except KeyError:
        bpy.data.materials.new(MAT_PREFIX + SUFFIX_marker)
        m = bpy.data.materials[MAT_PREFIX + SUFFIX_marker]
        format_os_material(m, sc.mat_color_m)
        # m.use_fake_user = True


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
    frame_numbers = [int(float(f.split('_')[-1])) for f in sk_names]
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
            if s.data.materials:
                s.data.materials[0] = mat
            else:
                s.data.materials.append(mat)
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
        OSkin.data.name = 'mos_' + obj.name + '_' + str(int(at_frame))
    if skin_type == 'MARKER':
        OSkin.name = 'marker_' + obj.name + '_' + str(int(at_frame))
        OSkin.data.name = 'mosm_' + obj.name + '_' + str(int(at_frame))


def make_duplicate_mesh(obj, parent_empty):
    sc = bpy.context.scene.onion_skins_scene_props
    if obj.type != "MESH":
        return False

    depsgraph = bpy.context.evaluated_depsgraph_get()
    tmp_obj_pose = obj.evaluated_get(depsgraph)

    newMesh = bpy.data.meshes.new_from_object(tmp_obj_pose)
    newMesh.transform(obj.matrix_world)
    OSkin = bpy.data.objects.new("object_name", newMesh)
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
    Skins = make_duplicate_mesh(obj, parent_empty)
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
            ob = bpy.data.objects[i.name]
            if not ob.library:
                print("OS: Object '" + i.name + "' does not exist in the current view layer ( Skiped )")
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
            ob = bpy.data.objects[i.name]
            if not ob.library:
                print("OS: Object '" + i.name + "' does not exists in the current view layer ( Skiped )")
                continue
        if ob.type == "MESH":
            bake = bake_gpu_mesh_piece(ob, curframe, at_frame, skin_type)
            if bake:
                Skins_count = Skins_count + 1
    return Skins_count


def remove_time_markers():
    tmarkers = bpy.context.scene.timeline_markers
    for m in tmarkers:
        if m.name == 'os':
            tmarkers.remove(m)


def remove_motion_paths(context, mode, only_selected=True):
    if mode == 'POSE':
        if mode != context.mode:
            bpy.ops.object.mode_set(mode='POSE')
            bpy.ops.pose.paths_clear(only_selected=False)
            bpy.ops.object.mode_set(mode=mode)
        else:
            bpy.ops.pose.paths_clear(only_selected=False)
    else:
        sc = bpy.context.scene.onion_skins_scene_props
        if sc.os_draw_mode == 'MESH':
            bpy.ops.object.paths_clear(only_selected=False)
        else:
            bpy.ops.object.paths_clear(only_selected=only_selected)


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


def calculate_motion_path(mode, display_type):
    if bpy.app.version < (3, 2, 0):
        exec(f"bpy.ops.{mode}.paths_calculate()")
    else:
        exec(f"bpy.ops.{mode}.paths_calculate(display_type=display_type)")


def create_update_motion_path(context, mode, obj, fs, fe, kfbefore, kfafter):
    sc = context.scene.onion_skins_scene_props
    curframe = context.scene.frame_current
    if sc.onionsk_mpath is False:
        #Remove if option is unchecked
        remove_motion_paths(context, mode)
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
        mp.frame_start = int(kfbefore[0])
        mp.frame_end = int(kfafter[af])
        mp.frame_step = int(kfafter[af]-kfbefore[0])
        fs = int(kfbefore[0])
        fe = int(kfafter[af])
        if bf < 0 or kfbefore[0] == -101010.0:  # NO BEFORE
            mp.frame_start = curframe
            mp.frame_step = int(kfafter[af])-curframe
            fs = curframe
        if af < 0 or kfafter[0] == 101010.0:  # NO AFTER
            mp.frame_end = curframe
            mp.frame_step = curframe-int(kfbefore[0])
            fe = curframe
    if sc.onionsk_method == 'SCENE':
        mp.type = 'RANGE'
        mp.frame_start = sc.onionsk_fr_start
        mp.frame_end = sc.onionsk_fr_end
        mp.frame_step = sc.onionsk_skip
    #Remove to Update MPath if already exists
    if mode == 'POSE':
        if mp.has_motion_paths is True:
            bpy.ops.pose.paths_clear(only_selected=False)
    elif mode == 'OBJECT':
        if mp.has_motion_paths is True:
            if sc.os_draw_mode == 'MESH':
                bpy.ops.object.paths_clear(only_selected=False)
            else:
                bpy.ops.object.paths_clear(only_selected=True)
    calculate_motion_path(mode.lower(), mp.type)
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
            context.scene.Status_progress = int(value)

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
    global Draw_Timer
    if Draw_Handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(Draw_Handler, 'WINDOW')
    if Draw_Timer is not None:
        context.window_manager.event_timer_remove(Draw_Timer)
    sc.draw_gpu_toggle = False
    Draw_Handler = None
    Draw_Timer = None


def create_handlers(self, context):
    global Draw_Handler
    global Draw_Timer
    Draw_Timer = context.window_manager.event_timer_add(0.1, window=context.window)
    Draw_Handler = bpy.types.SpaceView3D.draw_handler_add(
        self.draw_gpu_frames, (context,), 'WINDOW', 'POST_VIEW'
    )


class GPU_OT_Draw_Skins(Operator):
    bl_idname = "mos_op.gpu_draw_skins"
    bl_label = "GPU Draw Skins"
    bl_description = "Draw onion skins in 3D Viewport"
    bl_options = {'REGISTER'}

    def __init__(self):
        self.sc = bpy.context.scene.onion_skins_scene_props
        self.frames_count = None
        self.before = None
        self.after = None

    def invoke(self, context, event):
        if self.sc.os_draw_mode != 'GPU':
            return {'CANCELLED'}
        create_handlers(self, context)
        context.window_manager.modal_handler_add(self)
        obj = checkout_parent(context.active_object)

        if not GPU_FRAMES.get(obj.name):
            return {'RUNNING_MODAL'}
        self.frames_count = list(set(
            [(int(float(f.split('|@|')[-1])), i) for i, f in enumerate(GPU_FRAMES[obj.name])]
        ))
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
            if sc.onionsk_method == 'KEYFRAME' and sc.view_range_frame_type == 'KEYFRAME':
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

    def batch_draw(self, batch, skin_type=''):
        sc = bpy.context.scene.onion_skins_scene_props
        prefs = bpy.context.preferences.addons[__name__].preferences
        if bpy.app.version < (3, 0, 0):
            if not sc.gpu_mask_oskins and skin_type == 'ONION':
                bgl.glDepthMask(False)
            elif skin_type == 'ONION':
                bgl.glDepthMask(True)
            if not sc.gpu_mask_markers and skin_type == 'MARKER':
                bgl.glDepthMask(False)
            elif skin_type == 'MARKER':
                bgl.glDepthMask(True)
            bgl.glEnable(bgl.GL_DEPTH_TEST)
            if prefs.gl_cull_face:
                bgl.glEnable(bgl.GL_CULL_FACE)
            if not sc.gpu_flat_colors:
                bgl.glEnable(bgl.GL_BLEND)
            if sc.gpu_colors_in_front:
                bgl.glDepthRange(1, 0)

            batch.draw(SHADER)
            bgl.glDisable(bgl.GL_BLEND)
            bgl.glDisable(bgl.GL_CULL_FACE)
            bgl.glDisable(bgl.GL_DEPTH_TEST)
        else:
            if not sc.gpu_mask_oskins and skin_type == 'ONION':
                gpu.state.depth_mask_set(False)
            elif skin_type == 'ONION':
                gpu.state.depth_mask_set(True)
            if not sc.gpu_mask_markers and skin_type == 'MARKER':
                gpu.state.depth_mask_set(False)
            elif skin_type == 'MARKER':
                gpu.state.depth_mask_set(True)
            if sc.gpu_colors_in_front:
                gpu.state.depth_test_set('ALWAYS')
            else:
                gpu.state.depth_test_set('LESS_EQUAL')
            if prefs.gl_cull_face:
                gpu.state.face_culling_set('BACK')
            if not sc.gpu_flat_colors:
                gpu.state.blend_set('ALPHA')

            batch.draw(SHADER)
            if sc.gpu_mask_oskins and skin_type == 'ONION':
                gpu.state.depth_mask_set(False)
            if sc.gpu_mask_markers and skin_type == 'MARKER':
                gpu.state.depth_mask_set(False)

    def draw_gpu_frames(self, context):
        try:
            if not hasattr(self, 'sc'): pass
        except ReferenceError:
            remove_handlers(context)
            return None
        if not context.active_object or not context.space_data.overlay.show_overlays:
            return None
        curframe = context.scene.frame_current
        global SHADER
        sc = bpy.context.scene.onion_skins_scene_props
        prefs = bpy.context.preferences.addons[__name__].preferences
        obj = checkout_parent(context.active_object)
        colorB = sc.mat_color_bf
        colorA = sc.mat_color_af
        colorM = sc.mat_color_m
        if sc.hide_os_marker and GPU_MARKERS.get(obj.name):
            color = (colorM[0], colorM[1], colorM[2], colorM[3])
            SHADER.bind()
            SHADER.uniform_float("color", color)
            for i, item in enumerate(GPU_MARKERS[obj.name]):
                self.batch_draw(GPU_MARKERS[obj.name][item], 'MARKER')
        if not GPU_FRAMES.get(obj.name):
            return None
        for item in GPU_FRAMES[obj.name]:
            item_frame = float(item.split('|@|')[-1])
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
                if sc.view_range and sc.onionsk_method == 'KEYFRAME' and\
                        sc.view_range_frame_type == 'KEYFRAME' and\
                        sc.hide_os_before:
                    if item_frame in self.before:
                        draw = True
                elif frame_diff <= sc.view_before and sc.hide_os_before:
                    draw = True
            else:
                color = (colorA[0], colorA[1], colorA[2], colorA[3] - fade)
                if sc.view_range and sc.onionsk_method == 'KEYFRAME' and\
                        sc.view_range_frame_type == 'KEYFRAME' and\
                        sc.hide_os_after:
                    if item_frame in self.after:
                        draw = True
                elif frame_diff <= sc.view_after and sc.hide_os_after:
                    draw = True

            if curframe != item_frame and draw:
                SHADER.bind()
                SHADER.uniform_float("color", color)
                self.batch_draw(GPU_FRAMES[obj.name][item], 'ONION')


class Onion_Skins:

    keys_updated = {}
    keys_changed = []

    def __init__(self, obj=None, empty=None, cls=None):
        self.sc = bpy.context.scene.onion_skins_scene_props
        if not obj:
            self.obj = bpy.context.active_object
        else:
            self.obj = obj
        self.empty = empty
        self.cls = cls
        self.objp = checkout_parent(self.obj)
        self.curframe = bpy.context.scene.frame_current
        self._timer = None
        self.fs = 0
        self.fe = 0
        self.Frames = None
        self.Skins_count = 0

    def evaluate_frames(self, fs, fe, skip, isReverse, exclude):
        global CREATING
        CREATING = True
        skipthat = False
        if self.sc.onionsk_method == 'FRAME':
            if fs < 0:
                if self.curframe > 0:
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
            loopRange = range((lp), 0, -1)
        else:
            loopRange = range(1 + lp)
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~LOOP~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        Frames = []
        for lr in loopRange:
            if dolast and lr == lp:
                Frame = fe
            elif isReverse:
                Frame = (fe - ((lr) * skip))
                if fs + lr == 0 or Frame < fs:
                    Frame = fs
            else:
                Frame = fs + ((lr) * skip)
            if self.sc.onionsk_method == 'FRAME' and Frame == self.curframe:
                continue
            if skipthat and Frame == skip:
                continue
            if exclude == 1 and Frame == fs:
                continue
            if exclude == 2 and Frame == fe:
                continue
            Frames.append(Frame)
        return Frames

    def os_method_frame(self, dont_create=False):
        fs = self.curframe - self.sc.onionsk_fr_before
        fe = self.curframe
        if fs < 0:
            fs = 0
        skip = self.sc.onionsk_frame_step
        if not dont_create:
            FramesBf = self.evaluate_frames(fs, fe, skip, 1, 0)
        fs = self.curframe
        fe = self.curframe + self.sc.onionsk_fr_after
        if not dont_create:
            FramesAf = self.evaluate_frames(fs, fe, skip, 0, 0)
            self.fs = fs
            self.fe = fe
            return FramesBf + FramesAf
        return fs, fe

    def get_keyframes(self, action, full_keys=False):
        if not action:
            action = self.obj.animation_data.action
        all_keys = []
        for fcurve in action.fcurves:
            keys = fcurve.keyframe_points
            if self.sc.filter_keyframes and self.sc.filter_active_bone and \
                    self.obj.type == 'ARMATURE':
                bone_fcurve_skip = run_filter_active_bone(self.obj, fcurve)
                if bone_fcurve_skip:
                    continue
            for key in keys:
                if self.sc.filter_keyframes:
                    key_skip = run_filter_keyframes(key)
                    if key_skip:
                        continue
                if full_keys:
                    all_keys.append((key.co[0], key.co[1]))
                else:
                    all_keys.append(key.co[0])
        if full_keys:
            return all_keys
        all_keys = list(set(all_keys))
        all_keys.sort()
        kfbefore = [key for key in all_keys if key < self.curframe]
        kfafter = [key for key in all_keys if key > self.curframe]
        return kfbefore, kfafter, all_keys

    def os_method_keyframe(self, dont_create=False):
        bf = self.sc.onionsk_kfr_before
        af = self.sc.onionsk_kfr_after
        if hasattr(self.obj.animation_data, 'action'):
            action = self.obj.animation_data.action
        else:
            action = self.objp.animation_data.action
        if not hasattr(action, 'fcurves'):
            if not dont_create and self.cls:
                msg = "Mesh Onion Skins: Keyframes didn't found. Use Edit strip mode of the action if animation data is not empty."
                self.cls.report({'ERROR'}, msg)
            return False
        kfbefore, kfafter, all_keys = self.get_keyframes(action)

        if len(kfbefore) == 0 and len(kfafter) == 0:
            if not dont_create and self.cls:
                msg = "Mesh Onion Skins: Required Keyframes didn't found."
                self.cls.report({'WARNING'}, msg)
            return False

        if not self.sc.use_all_keyframes:
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
            bf = len([k for k in all_keys if k < self.curframe])
            af = len([k for k in all_keys if k > self.curframe])

        if len(kfbefore) == 0:
            kfbefore.append(-101010.0)
            bf = 0
        if len(kfafter) == 0:
            kfafter.append(101010.0)
            af = 0
        if dont_create:
            return kfbefore, kfafter, all_keys

        if (bf > af):
            FramesB = []
            if af > 0:
                for i in range(af):
                    FramesA = self.evaluate_frames(
                        kfbefore[i],
                        kfafter[i],
                        kfafter[i] - kfbefore[i],
                        0, 0
                    )
                    FramesB = FramesB + FramesA
            for i in range(af, bf):
                FramesA = self.evaluate_frames(
                    kfbefore[i],
                    kfafter[len(kfafter) - 1],
                    kfafter[len(kfafter) - 1] - kfbefore[i],
                    0, 2
                )
                FramesB = FramesB + FramesA
            Frames = FramesB

        if (bf < af):
            FramesB = []
            if bf > 0:
                for i in range(bf):
                    FramesA = self.evaluate_frames(
                        kfbefore[i],
                        kfafter[i],
                        kfafter[i] - kfbefore[i],
                        0, 0
                    )
                    FramesB = FramesB + FramesA
            for i in range(bf, af):
                FramesA = self.evaluate_frames(
                    kfbefore[len(kfbefore) - 1],
                    kfafter[i],
                    kfafter[i] - kfbefore[len(kfbefore) - 1],
                    0, 1
                )
                FramesB = FramesB + FramesA
            Frames = FramesB
        if (bf == af):
            FramesB = []
            for i in range(af):
                FramesA = self.evaluate_frames(
                    kfbefore[i],
                    kfafter[i],
                    kfafter[i] - kfbefore[i],
                    0, 0
                )
                FramesB = FramesB + FramesA
            Frames = FramesB
        self.kfbefore = kfbefore
        self.kfafter = kfafter
        if self.sc.use_all_keyframes:
            if float(self.curframe) in all_keys:
                Frames.append(float(self.curframe))
        Frames.sort()
        return Frames

    def os_method_range(self, context, dont_create=False):
        self.fs = self.sc.onionsk_fr_start
        self.fe = self.sc.onionsk_fr_end
        self.skip = self.sc.onionsk_skip
        # use playback range?
        if self.sc.onionsk_fr_sc:
            self.fs = context.scene.frame_start
            self.fe = context.scene.frame_end
        if self.sc.onionsk_action_range:
            all_keys = self.os_method_keyframe(dont_create=True)
            if not all_keys and self.cls:
                msg = "Mesh Onion Skins: Keyframes didn't found. Use Edit strip mode of the action if animation data is not empty."
                self.cls.report({'ERROR'}, msg)
                return False
            elif not all_keys:
                if dont_create:
                    return False, False
                return False
            self.fs = all_keys[2][0]
            self.fe = all_keys[2][-1]
        # fix start to end
        if self.fe < self.fs:
            swap = self.fs
            self.fs = self.fe
            self.fe = swap
        if dont_create:
            return self.fs, self.fe
        return self.evaluate_frames(
            self.fs, self.fe, self.skip, 0, 0)

    def set_frames(self, context):
        if self.sc.onionsk_method == 'FRAME':
            self.Frames = self.os_method_frame()
        if self.sc.onionsk_method == 'SCENE':
            self.Frames = self.os_method_range(context)
        if self.sc.onionsk_method == 'KEYFRAME':
            self.Frames = self.os_method_keyframe()

    def make_frame(self, Frame):
        bpy.context.scene.frame_set(int(Frame))
        print("Onion Skin: Frame " + str(Frame))
        if self.sc.os_draw_mode == 'MESH':
            count = make_onionSkin_frame(self, self.objp, self.empty, self.curframe, Frame)
        if self.sc.os_draw_mode == 'GPU':
            count = make_gpu_frame(self.objp, self.curframe, Frame)
        self.Skins_count += count


class OS_OT_CreateUpdate_Skins(Operator):
    bl_label = 'Update Onion Skins'
    bl_idname = 'mos_op.make_skins'
    bl_description = "Update Mesh Onion Skins for the selected object"
    bl_options = {'REGISTER', 'UNDO'}

    empty = None
    _timer = None
    th = None
    prog = 0
    stop_early = False
    loopIter = 0
    processing = False
    job_done = False

    def __init__(self):
        self.sc = bpy.context.scene.onion_skins_scene_props
        self.params = bpy.context.window_manager.onionSkinsParams
        self.obj = bpy.context.active_object
        self.objp = checkout_parent(self.obj)
        self.OSkins = None
        self.Frames = []
        self.Skins_count = 0
        self.keys_changed = Onion_Skins.keys_changed

    def modal(self, context, event):
        if event.type in {'ESC'}:  # 'RIGHTMOUSE',
            self.cancel(context)
            self.stop_early = True
            self.th.join()
            self.Skins_count = self.OSkins.Skins_count
            if self.params.auto_update_skins_toggle:
                self.auto_update_count()
            self.finishing(context)
            print('CANCELLED')

            return {'CANCELLED'}

        if event.type == 'TIMER':
            if self.processing:
                self.OSkins.make_frame(self.Frames[self.loopIter])
                print(str(int(self.prog)) + '%')
                self.processing = False

            if bpy.app.version < (2, 9, 3):
                is_alive = self.th.isAlive()
            else:
                is_alive = self.th.is_alive()
            if not is_alive:
                self.th.join()
                self.Skins_count = self.OSkins.Skins_count
                if self.params.auto_update_skins_toggle:
                    self.auto_update_count()
                self.finishing(context)
                # print('DONE')
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def get_update_frames(self):
        sc = bpy.context.scene.onion_skins_scene_props
        update_Frames = []
        kfbefore, kfafter, all_keys = self.OSkins.get_keyframes(None)
        if sc.auto_update_single_frame:
            if float(self.curframe) in all_keys:
                return update_Frames + [float(self.curframe)]
            else:
                return []
        if sc.auto_update_view_range:
            before = sc.view_before
            after = sc.view_after
        else:
            before = sc.auto_update_before
            after = sc.auto_update_after
        if kfbefore:
            if len(kfbefore) >= before:
                update_Frames = kfbefore[-before:]
            else:
                update_Frames = kfbefore
        if float(self.curframe) in all_keys:
            update_Frames += [float(self.curframe)]
        if kfafter:
            if len(kfafter) >= after:
                update_Frames += kfafter[0:after]
            else:
                update_Frames += kfafter
        return update_Frames

    def set_auto_update_frames(self, created_frames):
        sc = bpy.context.scene.onion_skins_scene_props
        if sc.auto_update_complete:
            return None
        update_Frames = self.get_update_frames()
        if update_Frames:
            self.Frames = [
                frame for frame in self.OSkins.Frames
                if frame >= update_Frames[0] and frame <= update_Frames[-1] or frame not in created_frames
            ]
        else:
            self.Frames = []
        self.Frames += [fr for fr in self.keys_changed if fr not in self.Frames]
        Onion_Skins.keys_changed.clear()

    def gpu_auto_update_frames(self):
        objp = self.objp
        global GPU_FRAMES
        created_frames = [float(item.split('|@|')[-1]) for item in GPU_FRAMES[objp.name]]
        self.set_auto_update_frames(created_frames)
        remove_items = []
        for item in GPU_FRAMES[objp.name]:
            item_frame = float(item.split('|@|')[-1])
            if item_frame not in self.OSkins.Frames or\
                    item_frame in self.Frames:
                remove_items.append(item)
        for i in remove_items:
            GPU_FRAMES[objp.name].pop(i)

    def mesh_auto_update_frames(self):
        tree = get_empty_objs_tree()
        if not tree:
            return None
        created_frames = [float(s.name.split('_')[-1]) for s in tree.children]
        self.set_auto_update_frames(created_frames)
        remove_items = []
        for s in tree.children:
            item_frame = float(s.name.split('_')[-1])
            if item_frame < self.curframe:
                s.name = '_'.join(['before'] + s.name.split('_')[1:])
            else:
                s.name = '_'.join(['after'] + s.name.split('_')[1:])
            if item_frame not in self.OSkins.Frames or\
                    item_frame in self.Frames:
                remove_items.append(s)
        for x in remove_items:
            mesh = x.data
            bpy.data.objects.remove(x, do_unlink=True)
            if bpy.data.meshes[mesh.name].users == 0:
                bpy.data.meshes.remove(mesh)

    def execute(self, context):

        sc = bpy.context.scene.onion_skins_scene_props
        params = bpy.context.window_manager.onionSkinsParams
        prefs = bpy.context.preferences.addons[__name__].preferences
        self.mode = context.mode
        self.curframe = context.scene.frame_current
        obj = self.obj
        # Check object is a parent or a child
        objp = self.objp
        if objp.type == 'ARMATURE' and\
                not context.window_manager.os_childrens_collection:
            msg = "Mesh Onion Skins: Mesh type objects didn't found."
            self.report({'ERROR'}, msg)
            return {'FINISHED'}

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

        remove_handlers(context)
        if not params.auto_update_skins_toggle:
            remove_skins(obj)
            if GPU_FRAMES.get(objp.name):
                GPU_FRAMES[objp.name].clear()

        #!!!!!!!!!!!!!!SET TO CONTEXT OBJECT MODE !!!!!!!!!!!!!!!!!
        #Store current mode to return to it after complete operations
        bpy.ops.object.mode_set(mode='OBJECT')
        if sc.os_draw_mode == 'MESH':
            # Initially Create Collectiont for skins to be stored in
            main_empty = init_os_collection()
            # Create an EMPTY using onionsk + Parent object's name
            self.empty = create_skins_empty(objp, 'ONION')
            if not self.empty:
                msg = "Mesh Onion Skins collection or parent Empty is hidden, make sure it is visible in View Layer"
                self.report({'ERROR'}, msg)
                return self.finishing(context)

        self.OSkins = Onion_Skins(obj, self.empty, cls=self)
        # Setup the Colored Materials for Skins
        create_skins_materials()

        obj.select_set(False)

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

        self.OSkins.set_frames(context)
        self.Frames = self.OSkins.Frames
        if not self.Frames:
            return self.finishing(context)

        self.th = threading.Thread(target=long_task, args=(self, context))

        if sc.os_draw_mode == 'GPU':
            if not GPU_FRAMES.get(objp.name):
                GPU_FRAMES[objp.name] = {}
            params.display_progress = False
            if params.auto_update_skins_toggle and obj.is_onionsk:
                self.gpu_auto_update_frames()
        if sc.os_draw_mode == 'MESH':
            if params.auto_update_skins_toggle and obj.is_onionsk:
                self.mesh_auto_update_frames()

        if params.display_progress:
            Progress_Status.show(self, context)
            self.th.start()
            wm = context.window_manager
            self._timer = wm.event_timer_add(0.1, window=context.window)
            wm.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            for Frame in self.Frames:
                self.OSkins.make_frame(Frame)
            self.Skins_count = self.OSkins.Skins_count
            if params.auto_update_skins_toggle:
                self.auto_update_count()
            print("Onion Skin: Done")
            return self.finishing(context)

    def auto_update_count(self):
        if not self.Frames and self.obj.is_onionsk:
            self.Skins_count = self.objp.onionsk_Skins_count
            self.Frames = self.OSkins.Frames
        else:
            frame_skins = self.OSkins.Skins_count / len(self.Frames)
            self.Skins_count = frame_skins * len(self.OSkins.Frames)
        if not self.obj.is_onionsk or\
                not Onion_Skins.keys_updated.get(self.obj.name):
            action = self.obj.animation_data.action
            keys = self.OSkins.get_keyframes(action, full_keys=True)
            Onion_Skins.keys_updated[self.obj.name] = keys

    def finishing(self, context):
        sc = bpy.context.scene.onion_skins_scene_props
        params = bpy.context.window_manager.onionSkinsParams
        obj = self.obj
        objp = self.objp
        mode = self.mode
        #////////////////////////////////////////////
        context.scene.frame_set(self.curframe)
        # update active Skins count
        objp.onionsk_Skins_count = int(self.Skins_count)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        if self.Frames and self.OSkins:
            # Object custom property of using Onion Skins
            obj.is_onionsk = True
            objp.is_onionsk = True
            set_onion_colors('BEFORE')
            set_onion_colors('AFTER')
            # Turn off view_range, otherwise it slows down motion path creation
            is_view_range = sc.view_range
            if is_view_range and sc.os_draw_mode == 'MESH':
                sc.view_range = False
            # CREATE MOTION PATH
            if sc.onionsk_mpath is True:
                if sc.onionsk_method == 'FRAME' or sc.onionsk_method == 'SCENE':
                    create_update_motion_path(
                        context, mode, obj,
                        self.OSkins.fs, self.OSkins.fe, [], [])
                if sc.onionsk_method == 'KEYFRAME':
                    create_update_motion_path(
                        context, mode, obj, 0, 0,
                        self.OSkins.kfbefore, self.OSkins.kfafter)
            if is_view_range and sc.os_draw_mode == 'MESH':
                sc.view_range = is_view_range

        # CREATE TIMELINE'S MARKER AT FRAME
        if self.sc.onionsk_tmarker and self.OSkins:
            for Frame in self.OSkins.Frames:
                tmarkers = bpy.context.scene.timeline_markers
                tmarkers.new("os", frame=int(Frame))

        bpy.data.objects.update()
        bpy.data.scenes.update()

        # Count all Onion Skins in scene exept Markers
        Skins = 0
        for o in context.scene.objects:
            if not hasattr(o, 'onionsk_Skins_count'):
                continue
            if o.onionsk_Skins_count > 0:
                Skins = Skins + o.onionsk_Skins_count
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

        if sc.os_draw_mode == 'GPU' and not sc.draw_gpu_toggle:
            sc.draw_gpu_toggle = True
        global CREATING
        CREATING = False
        if sc.view_range:
            view_range_frames(context.scene)

        if not params.display_progress and self.empty:
            msg = "Mesh Onion Skins Updated"
            self.report({'INFO'}, msg)

        return {'FINISHED'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        Progress_Status.hide(self)


class OS_OT_Remove_Skins(Operator):
    bl_label = 'Remove Skins'
    bl_idname = 'mos_op.remove_skins'
    bl_description = "Delete Mesh Onion Skins for the selected Object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        sc = bpy.context.scene.onion_skins_scene_props
        #Remove timeline_markers
        tmarkers = bpy.context.scene.timeline_markers
        imarkers = tmarkers.items()
        for m in imarkers:
            if (m[0] == 'os'):
                tmarkers.remove(tmarkers.get('os'))
        mode = context.mode
        remove_motion_paths(context, mode)
        # REMOVE Skins ////////
        remove_skins(obj)
        objp = checkout_parent(obj)
        if not objp.is_os_marker and not GPU_MARKERS.get(objp.name):
            sc.draw_gpu_toggle = False
        global GPU_FRAMES
        if GPU_FRAMES.get(objp.name):
            GPU_FRAMES[objp.name].clear()

        bpy.data.objects.update()
        bpy.context.scene.objects.update()

        # count all skins in scene
        Skins = 0
        for o in bpy.context.scene.objects:
            if not hasattr(o, 'onionsk_Skins_count'):
                continue
            if o.onionsk_Skins_count > 0:
                Skins = Skins + o.onionsk_Skins_count
        sc.onionsk_Skins_count = Skins

        # msg = "Mesh Onion Skins Removed from Object"
        # self.report({'INFO'}, msg)

        return {'FINISHED'}


class OS_OT_Add_Marker(Operator):
    bl_label = 'Add Marker'
    bl_idname = 'mos_op.add_marker'
    bl_description = "Add a marker skin at the current frame"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        sc = bpy.context.scene.onion_skins_scene_props
        params = bpy.context.window_manager.onionSkinsParams
        obj = context.active_object
        # Check to see if object is a parent or a child
        objp = checkout_parent(obj)
        tmarkers = bpy.context.scene.timeline_markers
        curframe = bpy.context.scene.frame_current
        # start at current frame
        if sc.onionsk_tmarker is True:
            tmarkers.new("osm", frame=curframe)

        if sc.os_draw_mode == 'GPU':
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

        if sc.os_draw_mode == 'MESH':
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
        if mark_skins_empty and sc.os_draw_mode == 'MESH':
            count = make_onionSkin_frame(self, objp, mark_skins_empty, curframe, curframe, 'MARKER')
        elif sc.os_draw_mode == 'GPU':
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


class OS_OT_Remove_Marker(Operator):
    bl_label = 'Remove Markers'
    bl_idname = 'mos_op.remove_marker'
    bl_description = "Remove Markers from the selected object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        obj = context.active_object

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

        for area in context.window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        # msg = "Mesh Onion Markers Removed"
        # self.report({'INFO'}, msg)

        return {'FINISHED'}


class OS_OT_Update_Motion_Path(Operator):
    bl_label = 'Update Motion Path'
    bl_idname = 'mos_op.update_motion_path'
    bl_description = "Update motion path for the selected object"

    def execute(self, context):
        update_mpath(self, context)
        return {'FINISHED'}


class OS_OT_Clear_Motion_Path(Operator):
    bl_label = 'Clear Motion Path'
    bl_idname = 'mos_op.clear_motion_path'
    bl_description = "Clear motion path for the selected object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        remove_motion_paths(context, context.mode)
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
        if hasattr(obj, "proxy"):
            if obj.proxy:
                obj = obj.proxy
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


class OBJECT_active_list_types(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="object name")
    active_list_type: bpy.props.StringProperty(name="list type")


class WM_OT_list_uncheck_all(Operator):
    bl_label = 'Uncheck All'
    bl_idname = 'wm.os_uncheck_all_children_list'
    bl_description = "Uncheck all in the childrens list"

    def execute(self, context):
        check_uncheck_all_object_collection_items(flag="uncheck")
        return {'FINISHED'}


class WM_OT_list_check_all(Operator):
    bl_label = 'Check All'
    bl_idname = 'wm.os_check_all_children_list'
    bl_description = "Check all in the childrens list"
    # bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        check_uncheck_all_object_collection_items(flag="check")
        return {'FINISHED'}


class WM_OT_list_save_settings(Operator):
    bl_label = 'Save List Settings'
    bl_idname = 'wm.os_save_list_settings'
    bl_description = "Save settings of the childrens list for the current object"

    def execute(self, context):
        save_os_list_settings()
        return {'FINISHED'}


class WM_OT_list_load_settings(Operator):
    bl_label = 'Load List Settings'
    bl_idname = 'wm.os_load_list_settings'
    bl_description = "Load settings of the childrens list for the current object"

    def execute(self, context):
        load_os_list_settings()
        return {'FINISHED'}


class WM_OT_update_childrens_list(Operator):
    bl_label = 'Update Childrens List'
    bl_idname = 'wm.os_update_childrens_list'
    bl_description = "Update the childrens list of the active object"

    def execute(self, context):
        update_object_data_collection_items()
        return {'FINISHED'}


class WM_OT_object_list_settings_remove(Operator):
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

    auto_update_before: IntProperty(
        name="Before",
        description='Set keyframe range before current frame, that being used by auto update onion skins',
        min=0, soft_min=0, max=10000, soft_max=10000, default=2)

    auto_update_after: IntProperty(
        name="After",
        description='Set keyframe range after current frame, that being used by auto update onion skins',
        min=0, soft_min=0, max=10000, soft_max=10000, default=2)

    auto_update_single_frame: BoolProperty(
        name='Single Frame',
        description='The auto update gonna use a single current frame only',
        default=False,
        update=update_auto_update_single)

    auto_update_view_range: BoolProperty(
        name='Use View Range',
        description='The auto update gonna use a view range keyframes',
        default=False,
        update=update_auto_update_view)

    auto_update_complete: BoolProperty(
        name='Complete',
        description='The auto update gonna use a completely defined range of frames',
        default=False,)
        # update=update_auto_update_view)

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

    os_draw_mode: EnumProperty(
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
        description='Set type of frames for view range', default='KEYFRAME',
        update=update_view_range_frame_type)

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
    if sc.os_draw_mode == 'GPU':
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
    if sc.os_draw_mode == 'MESH':
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
        if sc.os_draw_mode == 'MESH':
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

    settings_preset_new_name: StringProperty(
        name="Name",
        default="New Preset"
    )
    auto_update_skins_toggle: BoolProperty(
        name="Auto Update Skins",
        description="Update skins automatically on change or inserting a new keyframe",
        default=False)


def update_pref_color_alpha(self, context):
    if not self.color_alpha:
        self.fade_to_alpha = False
    else:
        update_pref_color_alpha_value(self, context)


def update_pref_color_alpha_value(self, context):
    if self.color_alpha:
        self.mat_color_bf[3] = self.color_alpha_value
        self.mat_color_af[3] = self.color_alpha_value
        self.mat_color_m[3] = self.color_alpha_value


class Onion_Skins_Preferences(AddonPreferences):
    bl_idname = __name__

    category: StringProperty(
        name="Tab Category",
        description="Choose a name for the category of the panel",
        default="Animation",
        update=update_panel
    )
    mat_color_bf: FloatVectorProperty(
        name="Before",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(0.1, 0.1, 1, 0.3),
    )
    mat_color_af: FloatVectorProperty(
        name="After",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(1, 0.1, 0.1, 0.3),
    )
    mat_color_m: FloatVectorProperty(
        name="Marker",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(0, 0, 0, 0.3),
    )
    fade_to_alpha: BoolProperty(
        name="Fade to Alpha",
        description="Fade onion skins to the edges of the frame range",
        default=True)

    fade_to_value: FloatProperty(
        attr="fade_value",
        name="Fade value",
        description='Fade to Alpha color value',
        step=5,
        min=0.0, soft_min=0, max=1, soft_max=1, default=0.05,
    )

    color_alpha: BoolProperty(
        name="Alpha",
        description="Color alpha",
        default=True,)
        # update=update_pref_color_alpha)

    color_alpha_value: FloatProperty(
        attr="color_alpha_value",
        name="Alpha",
        description='Color alpha value',
        step=5,
        min=0.0, soft_min=0, max=1, soft_max=1, default=0.3,)
        # update=update_pref_color_alpha_value)

    display_progress: BoolProperty(
        name="Display Progress",
        description="Draw Technic: Mesh: Show progress in the window UI while creating onion skins ( creating is slower while turned on )",
        default=False)

    onionsk_tmarker: BoolProperty(
        name='Time Markers',
        description='Create time markers at frames',
        default=False)

    onionsk_mpath: BoolProperty(
        name='Motion Path',
        description='Show motion path of animated object',
        default=False)

    gl_cull_face: BoolProperty(
        name='GPU Backface Culling',
        description='Hide the back side of faces in GPU mode',
        default=False)

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
        name='View Range',
        description='Use the view range to show onion skins at a specific frame range around the current frame position and hide others',
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
        min=0, soft_min=0, max=10000, soft_max=10000, default=2,)
        # update=update_view_range)

    view_after: IntProperty(
        attr="view_after",
        name="Forward",
        description='View frames after current frame',
        min=0, soft_min=0, max=10000, soft_max=10000, default=2,)
        # update=update_view_range)

    onionsk_frame_step: IntProperty(
        attr="onionsk_frame_step",
        name="Frame Step",
        description='Frames to skip* (1 = draw every frame)\nFirst and last input frames is always included',
        min=1, soft_min=1, max=100, soft_max=100, default=5)

    onionsk_fr_sc: BoolProperty(
        attr="onionsk_fr_sc",
        name='Playback range',
        description='Use Start/End playback frames',
        default=False,)
        # update=update_in_range_playback)

    onionsk_action_range: BoolProperty(
        name='Action range',
        description='Use the current animation range',
        default=False,)
        # update=update_in_range_action)

    onionsk_skip: IntProperty(
        attr="onionsk_skip",
        name="Step",
        description='Frames to skip (1 = draw every frame)',
        min=1, soft_min=1, max=100, soft_max=100, default=1)

    use_all_keyframes: BoolProperty(
        name='All Keyframes',
        description='Use all keyframes of the current action to create onion skin at each of them',
        default=True)

    view_range_frame_type: EnumProperty(
        name="View Frame Type", items=[
            ('KEYFRAME', 'Keyframe',
             "Use the timeline keyframes for view range"),
            ('FRAME', 'Frame',
             "Use the timeline frames for view range")],
        description='Set type of frames for view range', default='KEYFRAME')

    os_draw_mode: EnumProperty(
        name="Draw Mode", items=[
            ('GPU', 'GPU',
             ''),
            ('MESH', 'Mesh',
             '')],
        description='Set draw mode', default='GPU')

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
        col.prop(self, 'mat_color_bf', text='')  # , text="Before"
        col = flow.column(align=True)
        col.label(text="After")
        col.prop(self, 'mat_color_af', text='')  # , text="After"
        col = flow.column(align=True)
        col.label(text="Marker")
        col.prop(self, 'mat_color_m', text='')
        row = box.row()
        row.prop(self, 'color_alpha')
        row.prop(self, 'color_alpha_value', text='')
        rowf = row.row()
        rowf.enabled = self.color_alpha
        rowf.prop(self, 'fade_to_alpha')
        row.prop(self, 'fade_to_value', text='')
        row = layout.row()
        row.prop(self, 'os_draw_mode')
        box = layout.box()
        box.label(text="Frames:")
        row = box.row()
        row.prop(self, 'onionsk_method', text='Method')

        if self.onionsk_method == 'FRAME':
            col = box.column(align=True)
            split = box.split()
            row = box.row()

            row = split.row(align=True)
            row.prop(self, "onionsk_fr_before", text="Before")
            row.prop(self, "onionsk_fr_after", text="After")
            row.prop(self, "onionsk_frame_step", text="Step")

        if self.onionsk_method == 'KEYFRAME':
            row = box.row()
            row.prop(self, "use_all_keyframes")
            col = box.column(align=True)
            split = box.split()
            row = box.row()

            row = split.row(align=True)
            row.enabled = not self.use_all_keyframes
            row.prop(self, "onionsk_kfr_before", text="Before")
            row.prop(self, "onionsk_kfr_after", text="After")

        if self.onionsk_method == 'SCENE':
            row = box.row()
            row.prop(self, "onionsk_fr_sc", toggle=True)
            row.prop(self, "onionsk_action_range", toggle=True)
            col = box.column(align=True)
            split = box.split()
            row = box.row()

            if self.onionsk_fr_sc or self.onionsk_action_range:
                row = split.row(align=True)
                row.prop(self, "onionsk_skip", text="Frame Step")
            else:
                row = split.row(align=True)
                row.prop(self, "onionsk_fr_start", text="Start")
                row.prop(self, "onionsk_fr_end", text="End")
                row.prop(self, "onionsk_skip", text="Step")
        row = box.row(align=True)
        row.prop(self, 'view_range')
        if self.onionsk_method == 'KEYFRAME':
            row = box.row(align=True)
            row.prop(self, 'view_range_frame_type', expand=True)
        row = box.row(align=True)
        row.prop(self, 'view_before')
        row.prop(self, 'view_after')

        row = layout.row()
        row.prop(self, 'onionsk_tmarker')
        row.prop(self, 'onionsk_mpath')
        row = layout.row()
        row.prop(self, 'gl_cull_face')
        row.prop(self, 'display_progress')

        row = layout.row(align=True)
        row.operator("mos_op.save_pref_settings", icon='EXPORT')
        row.operator("mos_op.load_pref_settings", icon='IMPORT')


class WM_OT_Show_Preferences(Operator):
    bl_label = 'Show Preference Settings'
    bl_idname = 'mos_op.show_pref_settings'
    bl_description = "Show add-on preference settings"

    def execute(self, context):
        import addon_utils

        addons = [
            (mod, addon_utils.module_bl_info(mod))
            for mod in addon_utils.modules(refresh=False)
        ]

        for mod, info in addons:
            # if mod.__name__ == "Mesh_Onion_Skins":
            if info['name'] == "Mesh Onion Skins":
                info['show_expanded'] = True

        bpy.context.preferences.active_section = 'ADDONS'
        bpy.data.window_managers["WinMan"].addon_filter = 'Animation'
        bpy.data.window_managers["WinMan"].addon_search = "Mesh Onion Skins"

        bpy.ops.screen.userpref_show()
        return {'FINISHED'}


def get_config_path():
    user_path = bpy.utils.resource_path('USER')
    config_path = os.path.join(user_path, "config")
    config_path = os.path.join(config_path, "mesh_onion_skins")
    if not os.path.isdir(config_path):
        os.mkdir(config_path, mode=0o777)
    return config_path


def get_file_list_names(path, extension='.json'):
    file_names = []
    for file in os.listdir(path):
        if os.path.isfile(os.path.join(path, file)) and\
                file.lower().endswith(extension):
            name = file.split(extension)[0]
            file_names.append(name)
    return file_names


def settings_preset_names(context):
    presets_path = os.path.join(get_config_path(), "presets")
    if not os.path.isdir(presets_path):
        os.mkdir(presets_path, mode=0o777)
    return get_file_list_names(presets_path)


def save_settings_to_file(source, file_path, skip_list=[]):
    pref_data = {}
    for pr in source.__annotations__:
        if pr in skip_list:
            continue
        value = eval("source." + pr)
        if type(value).__name__ == 'bpy_prop_array':
            pref_data[pr] = [v for v in value]
        else:
            pref_data[pr] = value

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(pref_data, f, ensure_ascii=False, indent=4)


def load_settings_from_file(load_to, file_path):
    f = open(file_path)
    pref_data = json.load(f)
    for pr in pref_data:
        value = pref_data.get(pr)
        exec("if hasattr(load_to, pr): load_to." + pr + " = value")
    f.close()


class PREF_OT_Save_Settings_Preset(Operator):
    bl_label = 'Save Settings Preset'
    bl_idname = 'mos_op.save_settings_preset'
    bl_description = "Save settings preset to a .json file"

    name: bpy.props.StringProperty(name="Name")

    def execute(self, context):
        sc = bpy.context.scene.onion_skins_scene_props
        presets_path = os.path.join(get_config_path(), "presets")
        file_name = self.name + '.json'
        file_path = os.path.join(presets_path, file_name)
        skip = [
            'os_draw_mode',
            'draw_gpu_toggle',
            'selection_sets',
            'show_parent_users_collection',
        ]
        save_settings_to_file(sc, file_path, skip_list=skip)

        msg = "Mesh Onion Skins: The preset has been saved to " + file_path
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class PREF_OT_Load_Settings_Preset(Operator):
    bl_label = 'Load Settings Preset'
    bl_idname = 'mos_op.load_settings_preset'
    bl_description = "Load settings preset from saved .json file"

    name: bpy.props.StringProperty(name="Name")

    def execute(self, context):
        sc = bpy.context.scene.onion_skins_scene_props
        presets_path = os.path.join(get_config_path(), "presets")
        file_name = self.name + '.json'
        file_path = os.path.join(presets_path, file_name)
        if not os.path.isfile(file_path):
            msg = "Mesh Onion Skins: The preset file '" + self.name + "' does not exist"
            self.report({'ERROR'}, msg)
            return {'FINISHED'}
        load_settings_from_file(sc, file_path)

        msg = "Mesh Onion Skins: The preset has been loaded from " + file_path
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class PREF_OT_Remove_Settings_Preset(Operator):
    bl_label = 'Remove Settings Preset'
    bl_idname = 'mos_op.remove_settings_preset'
    bl_description = "Remove settings preset and saved .json file"

    name: bpy.props.StringProperty(name="Name")

    def execute(self, context):
        presets_path = os.path.join(get_config_path(), "presets")
        file_name = self.name + '.json'
        file_path = os.path.join(presets_path, file_name)
        if not os.path.isfile(file_path):
            msg = "Mesh Onion Skins: The preset file '" + self.name + "' does not exist"
            self.report({'ERROR'}, msg)
            return {'FINISHED'}
        os.remove(file_path)

        msg = "Mesh Onion Skins: The preset file '" + file_name + "' has been removed"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class POPOVER_PT_Settings_Presets(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'HEADER'
    bl_label = "Settings Presets"
    bl_idname = "POPOVER_PT_settings_presets"

    def draw(self, context):
        params = context.window_manager.onionSkinsParams
        layout = self.layout
        layout.emboss = 'PULLDOWN_MENU'
        preset_names = settings_preset_names(context)
        for name in preset_names:
            row = layout.row(align=True)
            row.operator('mos_op.load_settings_preset', text=name).name = name
            row.operator('mos_op.remove_settings_preset', text='', icon='REMOVE').name = name
        row = layout.row(align=False)
        row.emboss = 'NORMAL'
        row.prop(params, "settings_preset_new_name", text='')
        sub_row = row.row(align=False)
        sub_row.emboss = 'PULLDOWN_MENU'
        op = sub_row.operator('mos_op.save_settings_preset', text='', icon='ADD')
        op.name = params.settings_preset_new_name


class POPOVER_PT_Auto_Update(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'HEADER'
    bl_label = "Auto Update Properties"
    bl_idname = "POPOVER_PT_auto_update"

    def draw(self, context):
        # params = context.window_manager.onionSkinsParams
        sc = bpy.context.scene.onion_skins_scene_props
        layout = self.layout
        row = layout.row(align=True)
        row.prop(sc, "auto_update_complete", toggle=True)
        row = layout.row(align=True)
        row.enabled = not sc.auto_update_complete
        row.prop(sc, "auto_update_single_frame", toggle=True)
        row.prop(sc, "auto_update_view_range", toggle=True)
        row = layout.row(align=True)
        if sc.auto_update_single_frame or\
                sc.auto_update_view_range or\
                sc.auto_update_complete:
            row.enabled = False
        row.prop(sc, "auto_update_before")
        row.prop(sc, "auto_update_after")


class PREF_OT_Save_Settings(Operator):
    bl_label = 'Save Settings'
    bl_idname = 'mos_op.save_pref_settings'
    bl_description = "Save preference settings to a json file"

    def execute(self, context):
        prefs = context.preferences.addons[__name__].preferences
        config_path = get_config_path()
        json_file = os.path.join(config_path, "mesh_onion_skins_settings.json")
        save_settings_to_file(prefs, json_file)

        msg = "Mesh Onion Skins: The settings has been saved to " + json_file
        self.report({'INFO'}, msg)

        return {'FINISHED'}


class PREF_OT_Load_Settings(Operator):
    bl_label = 'Load Settings'
    bl_idname = 'mos_op.load_pref_settings'
    bl_description = "Load preference settings from saved json file"

    def execute(self, context):
        prefs = context.preferences.addons[__name__].preferences
        config_path = get_config_path()
        json_file = os.path.join(config_path, "mesh_onion_skins_settings.json")
        if not os.path.isfile(json_file):
            msg = "Mesh Onion Skins: The settings file does not exist or it have not been saved yet"
            self.report({'WARNING'}, msg)
            return {'FINISHED'}
        load_settings_from_file(prefs, json_file)

        msg = "Mesh Onion Skins: The settings has been loaded from " + json_file
        self.report({'INFO'}, msg)

        return {'FINISHED'}


class WM_MT_List_Ops(Menu):
    bl_label = "List Operations"
    bl_idname = "WM_MT_List_ops_menu"

    def draw(self, context):
        layout = self.layout
        layout.operator("wm.os_save_list_settings", icon="FILE_TICK")
        layout.operator("wm.os_load_list_settings", icon="IMPORT")
        layout.separator()
        layout.operator("wm.os_list_settings_remove", icon='X')


class WM_MT_Marker_List_Popup(Operator):
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


def get_view_range_keyframes(curframe, tree_skin, frames_count):
    sc = bpy.context.scene.onion_skins_scene_props
    before_frames = sc.view_before - 1
    after_frames = sc.view_after - 1
    item_frame = int(float(tree_skin.name.split('_')[-1]))
    if item_frame < curframe:
        bf = [f for f in frames_count if f < curframe]
        bf.reverse()
        before = [f for i, f in enumerate(bf) if i <= before_frames]
        return before
    else:
        af = [f for f in frames_count if f > curframe]
        after = [f for i, f in enumerate(af) if i <= after_frames]
        return after


def view_range_frames(scene):
    global CREATING
    if CREATING:
        return None
    sc = bpy.context.scene.onion_skins_scene_props
    if not sc.view_range:
        return None
    if sc.os_draw_mode == 'GPU':
        return None
    tree = get_empty_objs_tree()
    if not tree:
        return None
    sk_names_before = []
    sk_names_after = []
    frames_count = list(set([(int(float(f.name.split('_')[-1])), i) for i, f in enumerate(tree.children)]))
    frames_count.sort()
    frames_count = dict(frames_count)
    for s in tree.children:
        if sc.onionsk_method == 'KEYFRAME' and sc.view_range_frame_type == 'KEYFRAME':
            item_frame = int(float(s.name.split('_')[-1]))
            if item_frame in get_view_range_keyframes(scene.frame_current, s, frames_count):
                if item_frame < scene.frame_current and sc.hide_os_before:
                    set_view_colors(s, 'before')
                    sk_names_before.append(s.name)
                    if s.hide_viewport:
                        s.hide_viewport = False
                    if sc.show_in_render:
                        s.hide_render = False
                    continue
                if item_frame > scene.frame_current and sc.hide_os_after:
                    set_view_colors(s, 'after')
                    sk_names_after.append(s.name)
                    if s.hide_viewport:
                        s.hide_viewport = False
                    if sc.show_in_render:
                        s.hide_render = False
                    continue
        else:
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
    if not scene.render.use_lock_interface and sc.os_draw_mode == 'MESH':
        scene.render.use_lock_interface = True
    view_range_frames(scene)


def m_os_post_render_handler(dummy):
    global RENDERING
    RENDERING = False


def m_os_cancel_render_handler(dummy):
    global RENDERING
    RENDERING = False


def is_onion_skin(obj):
    if not hasattr(obj, 'is_onionsk') and\
            not hasattr(obj, 'is_os_marker'):
        return None
    if obj.is_onionsk or obj.is_os_marker:
        return True
    else:
        return False


def check_update_active():
    if not poll_check(bpy.context):
        return None, None
    params = bpy.context.window_manager.onionSkinsParams
    if not params.onion_skins_init:
        return None, None
    global Active_Object
    try:
        if not hasattr(Active_Object, 'name'):
            Active_Object = None
    except ReferenceError:
        Active_Object = None
    last_obj = Active_Object
    if Active_Object != bpy.context.active_object:
        Active_Object = bpy.context.active_object
        return last_obj, True
    else:
        return last_obj, None


def set_childrens_list_selection_type(scene, last_obj):
    sc = scene.onion_skins_scene_props
    active_list_types = scene.os_object_active_list_types
    obj = bpy.context.active_object
    if last_obj:
        item_list_type = active_list_types.get(last_obj.name)
        if item_list_type:
            # Update last
            item_list_type.active_list_type = sc.selection_sets
        else:
            # Save last
            new_item = active_list_types.add()
            new_item.name = last_obj.name
            new_item.active_list_type = sc.selection_sets
    # Apply list type
    if active_list_types.get(obj.name):
        sc.selection_sets = active_list_types.get(obj.name).active_list_type
    else:
        sc.selection_sets = "PARENT"


def auto_update_skins(scene):
    global CREATING
    if CREATING:
        return None
    params = bpy.context.window_manager.onionSkinsParams
    sc = bpy.context.scene.onion_skins_scene_props
    if sc.os_draw_mode == 'GPU' and not sc.draw_gpu_toggle:
        return None
    if not params.auto_update_skins_toggle:
        return None
    if not poll_check(bpy.context):
        return None
    obj = bpy.context.active_object
    if not hasattr(obj, 'is_onionsk'):
        return None
    if not obj.is_onionsk:
        return None
    action = obj.animation_data.action
    OSkins = Onion_Skins()
    keys = OSkins.get_keyframes(action, full_keys=True)
    keys_upd = OSkins.keys_updated
    keys_changed = []
    if keys != keys_upd.get(obj.name):
        if keys_upd.get(obj.name):
            for i, key in enumerate(keys):
                try:
                    if not keys_upd.get(obj.name)[i][0]:
                        pass
                except IndexError:
                    continue
                if key[0] != keys_upd.get(obj.name)[i][0]:
                    continue
                if key[1] != keys_upd.get(obj.name)[i][1]:
                    keys_changed.append(key[0])
            keys_changed = list(set(keys_changed))
        Onion_Skins.keys_updated[obj.name] = keys
        Onion_Skins.keys_changed = keys_changed
        set_object_data_collection_items()
        bpy.ops.mos_op.make_skins()


def check_draw_gpu_toggle(scene):
    global Active_Object
    sc = scene.onion_skins_scene_props
    global DRAW_TOGGLE
    if sc.draw_gpu_toggle:
        DRAW_TOGGLE = True
    else:
        DRAW_TOGGLE = False
    if is_onion_skin(Active_Object):
        if sc.onionsk_tmarker:
            sc.onionsk_tmarker = False
            sc.onionsk_tmarker = True
        remove_handlers(bpy.context)
        if DRAW_TOGGLE and sc.os_draw_mode == 'GPU':
            sc.draw_gpu_toggle = True


def m_os_post_dpgraph_update(scene):
    last_obj, is_update = check_update_active()
    if is_update:
        set_childrens_list_selection_type(scene, last_obj)
    auto_update_skins(scene)
    if is_update:
        check_draw_gpu_toggle(scene)


@persistent
def m_os_on_file_load(scene):
    remove_handlers(bpy.context)
    global OS_Selected_Object_Sets
    global GPU_FRAMES
    global GPU_MARKERS
    global Active_Object
    global DRAW_TOGGLE
    OS_Selected_Object_Sets = {}
    GPU_FRAMES = {}
    GPU_MARKERS = {}
    Active_Object = None
    DRAW_TOGGLE = False


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
    OBJECT_active_list_types,
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
    WM_OT_Show_Preferences,
    PREF_OT_Save_Settings,
    PREF_OT_Load_Settings,
    POPOVER_PT_Settings_Presets,
    PREF_OT_Save_Settings_Preset,
    PREF_OT_Load_Settings_Preset,
    PREF_OT_Remove_Settings_Preset,
    POPOVER_PT_Auto_Update,
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
    bpy.types.Scene.os_object_active_list_types = bpy.props.CollectionProperty(type=OBJECT_active_list_types)

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
    del bpy.types.Scene.os_object_active_list_types
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
    except ValueError:
        pass
    try:
        bpy.app.handlers.save_pre.remove(m_os_pre_save)
    except ValueError:
        pass
    try:
        bpy.app.handlers.frame_change_post.remove(m_os_post_frames_handler)
    except ValueError:
        pass
    try:
        bpy.app.handlers.render_pre.remove(m_os_pre_render_handler)
    except ValueError:
        pass
    try:
        bpy.app.handlers.render_post.remove(m_os_post_render_handler)
    except ValueError:
        pass
    try:
        bpy.app.handlers.render_cancel.remove(m_os_cancel_render_handler)
    except ValueError:
        pass

    for panel in panels:
        bpy.utils.unregister_class(panel)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
