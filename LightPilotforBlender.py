bl_info = {
    "name": "Light Pilot",
    "author": "Buttercup Visuals//Mridul Sarmah",
    "version": (1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Light Pilot",
    "description": "This little handy tool gives you the freedom to control your lights like camera. This feature is inspired from Light Piloting inside Unreal Engine.",
    "category": "Lighting",
}

import bpy
from bpy.types import (
    Panel,
    Operator,
    AddonPreferences,
)
import mathutils
from bpy.app.handlers import persistent

# Global variables
is_piloting = False
piloted_light = None
previous_view_state = {}
handler_added = False

# Modal operator to continuously update light from viewport
class LIGHTPILOT_OT_pilot_light_modal(Operator):
    """Pilot the light by navigating in the viewport"""
    bl_idname = "light.pilot_modal"
    bl_label = "Pilot Light Modal"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}
    
    light_object: bpy.props.StringProperty()
    
    def modal(self, context, event):
        global is_piloting, piloted_light
        
        # Check if we should exit modal
        if not is_piloting or context.area.type != 'VIEW_3D':
            return self.cleanup(context)
        
        # Get the light we're piloting
        if self.light_object in bpy.data.objects:
            light_obj = bpy.data.objects[self.light_object]
            
            # Update the light position to match the viewport camera position (the viewer's eye)
            # This gets the exact position where the viewer is looking from, not just the pivot point
            view_matrix = context.region_data.view_matrix
            # The viewer's location is the inverted translation part of the view matrix
            viewer_location = view_matrix.inverted().translation
            light_obj.location = viewer_location
            
            # For directional lights, update rotation based on view direction
            if light_obj.data.type in ['SUN', 'SPOT', 'AREA']:
                # Get the view matrix to extract the exact forward direction of the viewport camera
                view_matrix = context.region_data.view_matrix
                # Extract the forward vector (negative z-axis of view matrix)
                forward = -view_matrix.to_3x3()[2].normalized()
                
                # Create rotation that points light in view direction
                quat = forward.to_track_quat('-Z', 'Y')
                
                # Apply rotation based on light's rotation mode
                if light_obj.rotation_mode == 'QUATERNION':
                    light_obj.rotation_quaternion = quat
                else:
                    light_obj.rotation_euler = quat.to_euler(light_obj.rotation_mode)
            
            # Handle specific hotkeys for the modal operator
            if event.type == 'ESC' and event.value == 'PRESS':
                return self.cleanup(context)
                
            # Force the sidebar to redraw to update any values
            for region in context.area.regions:
                if region.type == 'UI':
                    region.tag_redraw()
                    
        return {'PASS_THROUGH'}
    
    def cleanup(self, context):
        global is_piloting, piloted_light
        
        # Reset global states
        is_piloting = False
        piloted_light = None
        
        # Restore previous view state
        self.restore_view_state(context)
        
        # Clear active light property
        if "lightpilot_active_light" in context.scene:
            del context.scene["lightpilot_active_light"]
            
        # Report to user
        self.report({'INFO'}, "Exited light pilot mode")
        return {'FINISHED'}
        
    def restore_view_state(self, context):
        global previous_view_state
        
        if previous_view_state:
            if 'view_perspective' in previous_view_state:
                context.region_data.view_perspective = previous_view_state['view_perspective']
            if 'use_local_camera' in previous_view_state:
                context.space_data.use_local_camera = previous_view_state['use_local_camera']
            if 'camera' in previous_view_state and previous_view_state['camera']:
                context.space_data.camera = previous_view_state['camera']
            if 'view_location' in previous_view_state:
                context.region_data.view_location = previous_view_state['view_location']
            if 'view_rotation' in previous_view_state:
                context.region_data.view_rotation = previous_view_state['view_rotation']
            if 'view_distance' in previous_view_state:
                context.region_data.view_distance = previous_view_state['view_distance']
                
            # Clear stored state
            previous_view_state.clear()
    
    def invoke(self, context, event):
        global is_piloting, piloted_light, previous_view_state
        
        # Get the light to pilot
        if self.light_object in bpy.data.objects:
            light_obj = bpy.data.objects[self.light_object]
            
            # Store current view settings before switching to light piloting
            previous_view_state = {
                'view_location': context.region_data.view_location.copy(),
                'view_rotation': context.region_data.view_rotation.copy(),
                'view_distance': context.region_data.view_distance,
                'view_perspective': context.region_data.view_perspective,
                'use_local_camera': context.space_data.use_local_camera,
                'camera': context.space_data.camera,
            }
            
            # Set view perspective mode
            context.region_data.view_perspective = 'PERSP'
            context.space_data.use_local_camera = False
            
            # First we need to position the view pivot point at the light's location
            context.region_data.view_location = light_obj.location
            
            # Then adjust the view matrix to put the viewport camera at the light's exact position
            view_matrix = context.region_data.view_matrix.copy()
            # Set translation component so the viewer's eye is at the light's location
            # We'll use a small offset to avoid Blender's auto-adjustments
            context.region_data.view_distance = 0.001
            
            # Set rotation based on light type
            if light_obj.data.type in ['SUN', 'SPOT', 'AREA']:
                # Get the light's forward direction (-Z axis for lights)
                forward_vec = light_obj.matrix_world.to_quaternion() @ mathutils.Vector((0.0, 0.0, -1.0))
                forward_vec.normalize()
                
                # Create a rotation that points the view in the light's direction
                quat = forward_vec.to_track_quat('-Z', 'Y')
                context.region_data.view_rotation = quat
            else:
                # For point lights, use light's rotation or a default
                if light_obj.rotation_mode == 'QUATERNION':
                    context.region_data.view_rotation = light_obj.rotation_quaternion
                else:
                    context.region_data.view_rotation = light_obj.rotation_euler.to_quaternion()
            
            # Use minimal view distance so the viewer's eye is practically at the light position
            context.region_data.view_distance = 0.001
            
            # Set global state
            is_piloting = True
            piloted_light = light_obj
            
            # Store the light name in the scene for UI
            context.scene["lightpilot_active_light"] = light_obj.name
            
            # Report success
            self.report({'INFO'}, f"Now piloting light: {light_obj.name}")
            
            # Start the modal operator
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        
        self.report({'ERROR'}, "Could not find the specified light")
        return {'CANCELLED'}


class LIGHTPILOT_OT_pilot_light(Operator):
    """Start piloting the selected light interactively"""
    bl_idname = "light.pilot"
    bl_label = "Pilot Light"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        # Check if a light is selected
        return (context.object and 
                context.object.type == 'LIGHT')
    
    def execute(self, context):
        # Launch the modal operator
        bpy.ops.light.pilot_modal('INVOKE_DEFAULT', light_object=context.object.name)
        return {'FINISHED'}


class LIGHTPILOT_OT_exit_pilot(Operator):
    """Exit light piloting mode"""
    bl_idname = "light.exit_pilot"
    bl_label = "Exit Light Pilot"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        # Check if we're currently piloting a light
        global is_piloting
        return is_piloting
    
    def execute(self, context):
        # Set global piloting flag to False
        # The modal operator will detect this and clean up
        global is_piloting
        is_piloting = False
        return {'FINISHED'}


class LIGHTPILOT_PT_panel(Panel):
    """Light Pilot Panel"""
    bl_label = "Light Pilot"
    bl_idname = "LIGHTPILOT_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Light Pilot'
    
    def draw(self, context):
        layout = self.layout
        
        # Check if we're currently piloting a light
        global is_piloting, piloted_light
        
        if is_piloting and piloted_light:
            # UI for active piloting mode
            light_obj = piloted_light
            light_data = light_obj.data
            
            box = layout.box()
            box.label(text=f"Piloting: {light_obj.name}", icon='OUTLINER_OB_LIGHT')
            
            # Display light coordinates
            if context.scene.lightpilot_show_coords:
                coord_box = box.box()
                col = coord_box.column(align=True)
                col.label(text="Position:")
                col.prop(light_obj, "location", text="")
                
                # For directional lights, show direction
                if light_obj.data.type in ['SUN', 'SPOT', 'AREA']:
                    col.label(text="Direction:")
                    if light_obj.rotation_mode == 'QUATERNION':
                        col.prop(light_obj, "rotation_quaternion", text="")
                    else:
                        col.prop(light_obj, "rotation_euler", text="")
            
            # Exit button
            layout.operator("light.exit_pilot", icon='CANCEL')
            
            # Light controls
            box = layout.box()
            box.label(text="Light Settings:")
            
            # Light type display
            row = box.row()
            row.label(text=f"Type: {light_data.type}")
            
            # Common parameters
            box.prop(light_data, "energy", text="Power")
            box.prop(light_data, "color", text="Color")
            
            # Type-specific parameters
            if light_data.type == 'POINT':
                box.prop(light_data, "shadow_soft_size", text="Size")
            elif light_data.type == 'SPOT':
                box.prop(light_data, "shadow_soft_size", text="Size")
                box.prop(light_data, "spot_size", text="Spot Size")
                box.prop(light_data, "spot_blend", text="Spot Blend")
            elif light_data.type == 'SUN':
                box.prop(light_data, "angle", text="Angle")
            elif light_data.type == 'AREA':
                box.prop(light_data, "shape", text="Shape")
                if light_data.shape in {'RECTANGLE', 'ELLIPSE'}:
                    box.prop(light_data, "size", text="Size X")
                    box.prop(light_data, "size_y", text="Size Y")
                else:
                    box.prop(light_data, "size", text="Size")
            
            # Shadow settings
            box.prop(light_data, "use_shadow", text="Shadows")
            if light_data.use_shadow:
                box.prop(light_data, "shadow_buffer_clip_start", text="Clip Start")
                box.prop(light_data, "shadow_buffer_clip_end", text="Clip End")
            
        else:
            # UI for when not piloting
            # Show pilot button if a light is selected
            if context.object and context.object.type == 'LIGHT':
                layout.operator("light.pilot", icon='OUTLINER_OB_LIGHT')
            else:
                layout.label(text="Select a light to pilot")
        
        # Settings section
        box = layout.box()
        box.label(text="Settings:")
        box.prop(context.scene, "lightpilot_show_coords", text="Show Coordinates")


# Keymap registration
addon_keymaps = []

def register_keymaps():
    # Define keymap
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    
    if kc:
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        
        # Add keymap items
        # Alt+L to pilot selected light
        kmi = km.keymap_items.new("light.pilot", 'L', 'PRESS', alt=True)
        addon_keymaps.append((km, kmi))
        
        # Alt+Shift+L to exit pilot mode
        kmi = km.keymap_items.new("light.exit_pilot", 'L', 'PRESS', alt=True, shift=True)
        addon_keymaps.append((km, kmi))


def unregister_keymaps():
    # Remove keymap items
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()


# Register classes and properties
classes = (
    LIGHTPILOT_OT_pilot_light_modal,
    LIGHTPILOT_OT_pilot_light,
    LIGHTPILOT_OT_exit_pilot,
    LIGHTPILOT_PT_panel,
)

def register():
    # Register classes
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register properties
    bpy.types.Scene.lightpilot_show_coords = bpy.props.BoolProperty(
        name="Show Coordinates",
        description="Show light coordinates in the panel",
        default=True
    )
    
    # Register keymaps
    register_keymaps()

def unregister():
    # Unregister keymaps
    unregister_keymaps()
    
    # Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Unregister properties
    del bpy.types.Scene.lightpilot_show_coords
    
    # Ensure we clean up any active modal operation
    global is_piloting
    is_piloting = False

if __name__ == "__main__":
    register()
