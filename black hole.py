from direct.showbase.ShowBase import ShowBase
from panda3d.core import GeomVertexFormat, GeomVertexData, GeomVertexWriter
from panda3d.core import Geom, GeomPoints, GeomNode, Vec3
import math
import random


class ClickDragBlackHole(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        self.set_background_color(0, 0, 0)
        self.disable_mouse()

        # Camera Configuration
        self.camera_dist = 45.0
        self.camera_phi = math.radians(80)
        self.camera_theta = 0.0

        # Interaction State
        self.is_dragging = False
        self.last_mouse_pos = (0, 0)
        self.pulse_time = 0.0
        self.is_pulsing = False

        # 1. The Event Horizon
        self.horizon = self.loader.load_model("models/misc/sphere")
        self.horizon.reparent_to(self.render)
        self.horizon.set_scale(4.0)
        self.horizon.set_color(0, 0, 0, 1)

        # 2. Accretion Disk Data
        self.particles = []
        self.create_disk(num_particles=30000)
        self.create_starfield(1000)

        # 3. Input Controls
        self.accept("mouse1", self.on_click)
        self.accept("mouse1-up", self.on_release)
        self.accept("wheel_up", self.zoom_in)
        self.accept("wheel_down", self.zoom_out)

        self.taskMgr.add(self.update_simulation, "Update")

    def create_disk(self, num_particles):
        fmt = GeomVertexFormat.get_v3c4()
        vdata = GeomVertexData('disk', fmt, Geom.UH_dynamic)
        self.vertex_writer = GeomVertexWriter(vdata, 'vertex')
        self.color_writer = GeomVertexWriter(vdata, 'color')

        for i in range(num_particles):
            r = random.uniform(5.5, 18.0)
            angle = random.uniform(0, 2 * math.pi)
            speed = 2.8 / math.sqrt(r)
            y_offset = random.gauss(0, 0.1)

            t = (r - 5.5) / 12.5
            if t < 0.1:
                base_col = Vec3(0.9, 0.9, 1.0)
            elif t < 0.5:
                base_col = Vec3(1.0, 0.6, 0.1)
            else:
                base_col = Vec3(0.6, 0.1, 0.0)

            self.particles.append({
                'r': r, 'a': angle, 's': speed, 'y': y_offset,
                'base_col': base_col
            })
            self.vertex_writer.add_data3(0, 0, 0)
            self.color_writer.add_data4(base_col[0], base_col[1], base_col[2], 1.0)

        self.geom_node = GeomNode('bh_node')
        points = GeomPoints(Geom.UH_dynamic)
        points.add_next_vertices(num_particles)
        geom = Geom(vdata)
        geom.add_primitive(points)
        self.geom_node.add_geom(geom)
        self.bh_path = self.render.attach_new_node(self.geom_node)
        self.bh_path.set_render_mode_thickness(2)
        self.bh_path.set_light_off()

    def create_starfield(self, n):
        node = GeomNode('stars')
        vdata = GeomVertexData('stars', GeomVertexFormat.get_v3(), Geom.UH_static)
        writer = GeomVertexWriter(vdata, 'vertex')
        for _ in range(n):
            pos = Vec3(random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(-1, 1))
            pos.normalize()
            writer.add_data3(pos * 300)
        s_geom = Geom(vdata);
        s_pts = GeomPoints(Geom.UH_static)
        s_pts.add_next_vertices(n);
        s_geom.add_primitive(s_pts)
        node.add_geom(s_geom)
        self.render.attach_new_node(node).set_color(1, 1, 1, 1)

    def on_click(self):
        self.is_dragging = True
        if self.mouseWatcherNode.has_mouse():
            m_pos = self.mouseWatcherNode.get_mouse()
            self.last_mouse_pos = (m_pos.get_x(), m_pos.get_y())

        # Trigger the heat pulse effect
        self.is_pulsing = True
        self.pulse_time = 1.0

    def on_release(self):
        self.is_dragging = False

    def zoom_in(self):
        self.camera_dist = max(12, self.camera_dist - 2)

    def zoom_out(self):
        self.camera_dist = min(150, self.camera_dist + 2)

    def update_simulation(self, task):
        dt = globalClock.get_dt()

        # Update Pulse State
        if self.is_pulsing:
            self.pulse_time -= dt * 0.8
            if self.pulse_time <= 0: self.is_pulsing = False

        # 1. Camera Orbit (Only on Drag)
        if self.is_dragging and self.mouseWatcherNode.has_mouse():
            m_pos = self.mouseWatcherNode.get_mouse()
            dx = m_pos.get_x() - self.last_mouse_pos[0]
            dy = m_pos.get_y() - self.last_mouse_pos[1]

            self.camera_theta -= dx * 5.0  # Sensitivity
            self.camera_phi = max(0.1, min(math.pi - 0.1, self.camera_phi + dy * 2.0))
            self.last_mouse_pos = (m_pos.get_x(), m_pos.get_y())

        cam_pos = Vec3(
            self.camera_dist * math.sin(self.camera_phi) * math.cos(self.camera_theta),
            self.camera_dist * math.cos(self.camera_phi),
            self.camera_dist * math.sin(self.camera_phi) * math.sin(self.camera_theta)
        )
        self.camera.set_pos(cam_pos)
        self.camera.look_at(0, 0, 0)

        # 2. Update Geometry & Lensing
        vdata = self.geom_node.modify_geom(0).modify_vertex_data()
        vertex_view = GeomVertexWriter(vdata, 'vertex')
        color_view = GeomVertexWriter(vdata, 'color')
        normalized_cam = Vec3(cam_pos);
        normalized_cam.normalize()

        for p in self.particles:
            # Physics
            boost = (self.pulse_time * 4.0) if self.is_pulsing else 0.0
            p['a'] += (p['s'] + boost) * dt * 4.0
            real_pos = Vec3(p['r'] * math.cos(p['a']), p['y'], p['r'] * math.sin(p['a']))

            # Gravitational Lensing Warp
            dot_prod = real_pos.dot(normalized_cam)
            lensing_factor = 0.0
            if dot_prod < 0:
                lensing_factor = (8.0 / (real_pos.length() - 3.8)) * (abs(dot_prod) / self.camera_dist)

            visual_pos = Vec3(real_pos)
            visual_pos.y += lensing_factor * 12.0 * (1.0 if real_pos.y >= 0 else -1.0)
            vertex_view.set_data3(visual_pos)

            # Interactive Color
            display_col = p['base_col'] + (Vec3(0.4, 0.7, 1.0) * self.pulse_time if self.is_pulsing else Vec3(0))

            # Doppler Beaming
            vel_vec = Vec3(-math.sin(p['a']), 0, math.cos(p['a']))
            brightness = 1.0 + (vel_vec.dot(normalized_cam) * 0.6)
            final_c = display_col * brightness
            color_view.set_data4(final_c[0], final_c[1], final_c[2], 1.0)

        return task.cont


if __name__ == "__main__":
    app = ClickDragBlackHole()
    app.run()