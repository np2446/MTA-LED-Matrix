from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import ImageFont, ImageDraw, Image, ImageSequence
import numpy as np
import time
import threading
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict, Any, Callable
from enum import Enum
import colorsys
import math
import os

class ScrollDirection(Enum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"

class TextAlign(Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"

class TransitionEffect(Enum):
    NONE = "none"
    FADE = "fade"
    SLIDE = "slide"
    WIPE = "wipe"
    DISSOLVE = "dissolve"
    ZOOM = "zoom"

@dataclass
class TextStyle:
    """Configuration for text rendering"""
    font_path: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font_size: int = 12
    color: Tuple[int, int, int] = (255, 255, 255)
    background_color: Optional[Tuple[int, int, int]] = None
    outline_color: Optional[Tuple[int, int, int]] = None
    outline_width: int = 0
    shadow_color: Optional[Tuple[int, int, int]] = None
    shadow_offset: Tuple[int, int] = (2, 2)
    align: TextAlign = TextAlign.LEFT
    line_spacing: int = 2
    letter_spacing: int = 0

@dataclass
class AnimationConfig:
    """Configuration for animations"""
    duration: float = 5.0
    fps: int = 30
    loop: bool = True
    transition: TransitionEffect = TransitionEffect.NONE
    transition_duration: float = 0.5
    easing: str = "linear"  # linear, ease-in, ease-out, ease-in-out

class Layer:
    """Represents a drawable layer with position and effects"""
    def __init__(self, content: Image.Image, x: int = 0, y: int = 0, 
                 opacity: float = 1.0, blend_mode: str = "normal"):
        self.content = content
        self.x = x
        self.y = y
        self.opacity = opacity
        self.blend_mode = blend_mode
        self.visible = True
        self.effects = []

    def apply_effects(self):
        """Apply all effects to the layer"""
        result = self.content.copy()
        for effect in self.effects:
            result = effect(result)
        return result

class Effect:
    """Base class for visual effects"""
    def apply(self, image: Image.Image) -> Image.Image:
        raise NotImplementedError

class ColorEffect(Effect):
    """Applies color transformations"""
    def __init__(self, hue_shift: float = 0, saturation: float = 1.0, brightness: float = 1.0):
        self.hue_shift = hue_shift
        self.saturation = saturation
        self.brightness = brightness
    
    def apply(self, image: Image.Image) -> Image.Image:
        # Convert to HSV, apply transformations, convert back
        img_array = np.array(image)
        hsv = np.zeros_like(img_array, dtype=np.float32)
        
        for i in range(img_array.shape[0]):
            for j in range(img_array.shape[1]):
                r, g, b = img_array[i, j][:3] / 255.0
                h, s, v = colorsys.rgb_to_hsv(r, g, b)
                h = (h + self.hue_shift) % 1.0
                s = min(1.0, s * self.saturation)
                v = min(1.0, v * self.brightness)
                r, g, b = colorsys.hsv_to_rgb(h, s, v)
                img_array[i, j][:3] = [int(r * 255), int(g * 255), int(b * 255)]
        
        return Image.fromarray(img_array)

class AdvancedMatrixDisplay:
    def __init__(self, rows: int = 32, cols: int = 64, chain_length: int = 1,
                 parallel: int = 1, hardware_mapping: str = 'adafruit-hat',
                 gpio_slowdown: int = 2, brightness: int = 100):
        
        # Initialize matrix
        self.options = RGBMatrixOptions()
        self.options.rows = rows
        self.options.cols = cols
        self.options.chain_length = chain_length
        self.options.parallel = parallel
        self.options.hardware_mapping = hardware_mapping
        self.options.gpio_slowdown = gpio_slowdown
        self.options.brightness = brightness
        
        self.matrix = RGBMatrix(options=self.options)
        self.width = cols * chain_length
        self.height = rows * parallel
        
        # Display state
        self.layers: List[Layer] = []
        self.canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        self.is_running = False
        self.current_animation = None
        self.animation_thread = None
        
        # Font cache
        self.font_cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}
        
        # Effect processors
        self.global_effects = []
        
    def get_font(self, font_path: str, size: int) -> ImageFont.FreeTypeFont:
        """Get or cache a font"""
        key = (font_path, size)
        if key not in self.font_cache:
            self.font_cache[key] = ImageFont.truetype(font_path, size)
        return self.font_cache[key]
    
    def clear(self):
        """Clear the display and all layers"""
        self.layers.clear()
        self.matrix.Clear()
        self.canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
    
    def add_layer(self, layer: Layer) -> Layer:
        """Add a layer to the display"""
        self.layers.append(layer)
        return layer
    
    def remove_layer(self, layer: Layer):
        """Remove a layer from the display"""
        if layer in self.layers:
            self.layers.remove(layer)
    
    def composite_layers(self) -> Image.Image:
        """Composite all layers into a single image"""
        result = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        
        for layer in self.layers:
            if not layer.visible:
                continue
                
            # Apply layer effects
            layer_img = layer.apply_effects()
            
            # Apply opacity
            if layer.opacity < 1.0:
                alpha = layer_img.split()[-1]
                alpha = alpha.point(lambda p: p * layer.opacity)
                layer_img.putalpha(alpha)
            
            # Composite based on blend mode
            if layer.blend_mode == "normal":
                result.paste(layer_img, (layer.x, layer.y), layer_img)
            elif layer.blend_mode == "add":
                result = Image.blend(result, layer_img, layer.opacity)
            elif layer.blend_mode == "multiply":
                result = Image.composite(layer_img, result, layer_img)
        
        # Apply global effects
        for effect in self.global_effects:
            result = effect.apply(result)
        
        return result
    
    def render(self):
        """Render the current state to the matrix"""
        composite = self.composite_layers()
        rgb_image = composite.convert('RGB')
        self.matrix.SetImage(rgb_image)
    
    # Text rendering methods
    def create_text_image(self, text: str, style: TextStyle) -> Image.Image:
        """Create an image from text with the given style"""
        font = self.get_font(style.font_path, style.font_size)
        
        # Calculate text size
        dummy_img = Image.new("RGBA", (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)
        bbox = dummy_draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0] + abs(style.letter_spacing) * len(text)
        text_height = bbox[3] - bbox[1]
        
        # Create image with padding for effects
        padding = max(style.outline_width, 
                     abs(style.shadow_offset[0]) if style.shadow_color else 0,
                     abs(style.shadow_offset[1]) if style.shadow_color else 0) + 2
        
        img = Image.new("RGBA", (text_width + padding * 2, text_height + padding * 2), 
                       style.background_color or (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Draw shadow
        if style.shadow_color:
            draw.text((padding + style.shadow_offset[0], padding + style.shadow_offset[1]), 
                     text, font=font, fill=style.shadow_color)
        
        # Draw outline
        if style.outline_color and style.outline_width > 0:
            for dx in range(-style.outline_width, style.outline_width + 1):
                for dy in range(-style.outline_width, style.outline_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text((padding + dx, padding + dy), text, font=font, 
                                fill=style.outline_color)
        
        # Draw main text
        draw.text((padding, padding), text, font=font, fill=style.color)
        
        return img
    
    def add_text(self, text: str, x: int = 0, y: int = 0, 
                 style: Optional[TextStyle] = None) -> Layer:
        """Add static text to the display"""
        if style is None:
            style = TextStyle()
        
        text_img = self.create_text_image(text, style)
        layer = Layer(text_img, x, y)
        self.add_layer(layer)
        return layer
    
    def add_multiline_text(self, lines: List[str], x: int = 0, y: int = 0,
                          style: Optional[TextStyle] = None) -> List[Layer]:
        """Add multiple lines of text"""
        if style is None:
            style = TextStyle()
        
        layers = []
        current_y = y
        
        for line in lines:
            layer = self.add_text(line, x, current_y, style)
            layers.append(layer)
            current_y += style.font_size + style.line_spacing
        
        return layers
    
    # Image methods
    def add_image(self, image_path: str, x: int = 0, y: int = 0,
                  scale: Optional[float] = None, size: Optional[Tuple[int, int]] = None) -> Layer:
        """Add an image to the display"""
        img = Image.open(image_path)
        
        if size:
            img = img.resize(size, Image.Resampling.LANCZOS)
        elif scale:
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        layer = Layer(img.convert("RGBA"), x, y)
        self.add_layer(layer)
        return layer
    
    # Animation methods
    def scroll_text(self, text: str, style: Optional[TextStyle] = None,
                   direction: ScrollDirection = ScrollDirection.LEFT,
                   speed: float = 1.0, loop: bool = True):
        """Scroll text across the display"""
        if style is None:
            style = TextStyle()
        
        text_img = self.create_text_image(text, style)
        text_layer = Layer(text_img)
        self.add_layer(text_layer)
        
        def animation_func():
            if direction == ScrollDirection.LEFT:
                start_x = self.width
                end_x = -text_img.width
                step = -speed
            elif direction == ScrollDirection.RIGHT:
                start_x = -text_img.width
                end_x = self.width
                step = speed
            elif direction == ScrollDirection.UP:
                start_y = self.height
                end_y = -text_img.height
                step = -speed
            else:  # DOWN
                start_y = -text_img.height
                end_y = self.height
                step = speed
            
            while self.is_running:
                if direction in [ScrollDirection.LEFT, ScrollDirection.RIGHT]:
                    x = start_x
                    while (x > end_x if step < 0 else x < end_x) and self.is_running:
                        text_layer.x = int(x)
                        self.render()
                        x += step
                        time.sleep(1/60)  # 60 FPS
                else:
                    y = start_y
                    while (y > end_y if step < 0 else y < end_y) and self.is_running:
                        text_layer.y = int(y)
                        self.render()
                        y += step
                        time.sleep(1/60)
                
                if not loop:
                    break
        
        self.start_animation(animation_func)
    
    def fade_transition(self, from_layers: List[Layer], to_layers: List[Layer],
                       duration: float = 1.0):
        """Fade between two sets of layers"""
        def animation_func():
            steps = int(duration * 30)  # 30 FPS
            for i in range(steps + 1):
                alpha = i / steps
                
                # Fade out old layers
                for layer in from_layers:
                    layer.opacity = 1.0 - alpha
                
                # Fade in new layers
                for layer in to_layers:
                    layer.opacity = alpha
                
                self.render()
                time.sleep(1/30)
                
                if not self.is_running:
                    break
        
        self.start_animation(animation_func)
    
    def animate_gif(self, gif_path: str, x: int = 0, y: int = 0, 
                   scale: Optional[float] = None, loop: bool = True):
        """Display an animated GIF"""
        gif = Image.open(gif_path)
        frames = []
        
        for frame in ImageSequence.Iterator(gif):
            frame_rgba = frame.convert("RGBA")
            if scale:
                new_size = (int(frame_rgba.width * scale), int(frame_rgba.height * scale))
                # Use Image.LANCZOS for older Pillow versions (< 10.0.0)
                frame_rgba = frame_rgba.resize(new_size, Image.LANCZOS)
            frames.append(frame_rgba)
        
        def animation_func():
            while self.is_running:
                for frame in frames:
                    if not self.is_running:
                        break
                    
                    # Clear previous frame
                    self.clear()
                    layer = Layer(frame, x, y)
                    self.add_layer(layer)
                    self.render()
                    
                    # Use GIF frame duration if available
                    duration = gif.info.get('duration', 100) / 1000.0
                    time.sleep(duration)
                
                if not loop:
                    break
        
        self.start_animation(animation_func)
    
    def rainbow_effect(self, layer: Layer, speed: float = 1.0):
        """Apply a rainbow color cycling effect to a layer"""
        def animation_func():
            hue = 0
            while self.is_running:
                effect = ColorEffect(hue_shift=hue)
                layer.effects = [effect.apply]
                self.render()
                hue = (hue + speed * 0.01) % 1.0
                time.sleep(1/30)
        
        self.start_animation(animation_func)
    
    def pulse_effect(self, layer: Layer, min_opacity: float = 0.3, 
                    max_opacity: float = 1.0, speed: float = 1.0):
        """Apply a pulsing opacity effect to a layer"""
        def animation_func():
            t = 0
            while self.is_running:
                # Use sine wave for smooth pulsing
                opacity = min_opacity + (max_opacity - min_opacity) * \
                         (math.sin(t * speed) + 1) / 2
                layer.opacity = opacity
                self.render()
                t += 0.1
                time.sleep(1/30)
        
        self.start_animation(animation_func)
    
    def matrix_rain_effect(self, chars: str = "01", 
                          color: Tuple[int, int, int] = (0, 255, 0),
                          speed: float = 1.0):
        """Create a Matrix-style digital rain effect"""
        columns = self.width // 8  # Assuming 8px wide characters
        drops = [0] * columns
        
        def animation_func():
            font = self.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 10)
            
            while self.is_running:
                # Create semi-transparent black overlay for trail effect
                overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 50))
                overlay_layer = Layer(overlay)
                self.add_layer(overlay_layer)
                
                for i in range(columns):
                    char = chars[np.random.randint(0, len(chars))]
                    x = i * 8
                    y = drops[i] * 10
                    
                    if y < self.height and np.random.random() > 0.95:
                        text_img = Image.new("RGBA", (8, 10), (0, 0, 0, 0))
                        draw = ImageDraw.Draw(text_img)
                        draw.text((0, 0), char, font=font, fill=color)
                        
                        char_layer = Layer(text_img, x, y)
                        self.add_layer(char_layer)
                    
                    drops[i] += speed
                    if drops[i] * 10 > self.height and np.random.random() > 0.95:
                        drops[i] = 0
                
                self.render()
                time.sleep(0.05)
                
                # Clean up old layers periodically
                if len(self.layers) > 100:
                    self.layers = self.layers[-50:]
        
        self.start_animation(animation_func)
    
    def fire_effect(self, intensity: float = 1.0):
        """Create a fire/flame effect"""
        heat_map = np.zeros((self.height + 10, self.width))
        
        def animation_func():
            nonlocal heat_map
            
            while self.is_running:
                # Add random heat at the bottom
                heat_map[-1, :] = np.random.randint(150, 255, self.width) * intensity
                
                # Cool and rise
                for y in range(self.height + 9):
                    for x in range(self.width):
                        heat_map[y, x] = (
                            heat_map[y + 1, max(0, x - 1)] +
                            heat_map[y + 1, x] * 2 +
                            heat_map[y + 1, min(self.width - 1, x + 1)]
                        ) / 4.01
                
                # Convert heat to colors
                img = Image.new("RGB", (self.width, self.height))
                pixels = img.load()
                
                for y in range(self.height):
                    for x in range(self.width):
                        heat = int(heat_map[y, x])
                        if heat > 85:
                            pixels[x, y] = (255, 255, heat - 85)
                        elif heat > 35:
                            pixels[x, y] = (255, (heat - 35) * 5, 0)
                        elif heat > 0:
                            pixels[x, y] = (heat * 7, 0, 0)
                        else:
                            pixels[x, y] = (0, 0, 0)
                
                self.clear()
                self.add_layer(Layer(img))
                self.render()
                time.sleep(1/30)
        
        self.start_animation(animation_func)
    
    def particle_system(self, num_particles: int = 50, 
                       color: Tuple[int, int, int] = (255, 255, 255),
                       gravity: float = 0.1, lifetime: float = 3.0):
        """Create a particle system effect"""
        class Particle:
            def __init__(self):
                self.x = np.random.uniform(0, self.width)
                self.y = np.random.uniform(0, self.height)
                self.vx = np.random.uniform(-2, 2)
                self.vy = np.random.uniform(-5, -1)
                self.life = lifetime
                self.max_life = lifetime
            
            def update(self, dt):
                self.vx *= 0.99  # Air resistance
                self.vy += gravity
                self.x += self.vx * dt
                self.y += self.vy * dt
                self.life -= dt
                
                # Bounce off walls
                if self.x < 0 or self.x >= self.width:
                    self.vx *= -0.8
                    self.x = max(0, min(self.width - 1, self.x))
                
                if self.y >= self.height:
                    self.vy *= -0.8
                    self.y = self.height - 1
            
            def is_alive(self):
                return self.life > 0
        
        def animation_func():
            particles = [Particle() for _ in range(num_particles)]
            
            while self.is_running:
                img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                
                dt = 1/30
                for particle in particles:
                    particle.update(dt)
                    
                    if particle.is_alive():
                        alpha = int(255 * (particle.life / particle.max_life))
                        size = max(1, int(3 * (particle.life / particle.max_life)))
                        particle_color = (*color, alpha)
                        
                        draw.ellipse([
                            particle.x - size, particle.y - size,
                            particle.x + size, particle.y + size
                        ], fill=particle_color)
                    else:
                        # Respawn dead particle
                        particle.__init__()
                
                self.clear()
                self.add_layer(Layer(img))
                self.render()
                time.sleep(dt)
        
        self.start_animation(animation_func)
    
    def start_animation(self, animation_func: Callable):
        """Start an animation in a separate thread"""
        self.stop_animation()
        self.is_running = True
        self.animation_thread = threading.Thread(target=animation_func)
        self.animation_thread.daemon = True
        self.animation_thread.start()
    
    def stop_animation(self):
        """Stop the current animation"""
        self.is_running = False
        if self.animation_thread:
            self.animation_thread.join(timeout=1)
    
    def create_slideshow(self, content_list: List[Dict[str, Any]], 
                        duration_per_slide: float = 3.0,
                        transition: TransitionEffect = TransitionEffect.FADE):
        """Create a slideshow from a list of content"""
        def animation_func():
            while self.is_running:
                for content in content_list:
                    if not self.is_running:
                        break
                    
                    old_layers = self.layers.copy()
                    self.clear()
                    
                    # Add content based on type
                    if content['type'] == 'text':
                        self.add_text(content['text'], content.get('x', 0), 
                                    content.get('y', 0), content.get('style'))
                    elif content['type'] == 'image':
                        self.add_image(content['path'], content.get('x', 0),
                                     content.get('y', 0), content.get('scale'))
                    elif content['type'] == 'multiline':
                        self.add_multiline_text(content['lines'], content.get('x', 0),
                                              content.get('y', 0), content.get('style'))
                    
                    new_layers = self.layers.copy()
                    
                    # Apply transition
                    if transition == TransitionEffect.FADE and old_layers:
                        self.layers = old_layers + new_layers
                        for layer in new_layers:
                            layer.opacity = 0
                        
                        # Fade transition
                        steps = 30
                        for i in range(steps + 1):
                            alpha = i / steps
                            for layer in old_layers:
                                layer.opacity = 1.0 - alpha
                            for layer in new_layers:
                                layer.opacity = alpha
                            self.render()
                            time.sleep(1/30)
                        
                        self.layers = new_layers
                    else:
                        self.render()
                    
                    time.sleep(duration_per_slide)
        
        self.start_animation(animation_func)
    
    def save_frame(self, filename: str):
        """Save the current frame to a file"""
        composite = self.composite_layers()
        composite.save(filename)
    
    def __del__(self):
        """Cleanup on deletion"""
        self.stop_animation()
        self.clear()


# Example usage
if __name__ == "__main__":
    # Create display instance
    display = AdvancedMatrixDisplay(rows=32, cols=64, brightness=75)
    
    # Example 1: Static text with style
    style = TextStyle(
        font_size=14,
        color=(255, 200, 0),
        shadow_color=(50, 50, 50),
        shadow_offset=(2, 2)
    )
    display.add_text("Hello Matrix!", x=5, y=5, style=style)
    display.render()
    time.sleep(2)
    
    # Example 2: Scrolling text
    display.clear()
    display.scroll_text("Breaking News: Advanced Matrix Display System Launched!", 
                       style=TextStyle(color=(255, 0, 0), font_size=12),
                       direction=ScrollDirection.LEFT, speed=2.0)
    time.sleep(10)
    display.stop_animation()
    
    # Example 3: Fire effect
    display.clear()
    display.fire_effect(intensity=0.8)
    time.sleep(10)
    display.stop_animation()
    
    # Example 4: Slideshow
    display.clear()
    slideshow_content = [
        {'type': 'text', 'text': 'Slide 1', 'x': 10, 'y': 10},
        {'type': 'text', 'text': 'Slide 2', 'x': 20, 'y': 10, 
         'style': TextStyle(color=(0, 255, 0))},
        {'type': 'multiline', 'lines': ['Line 1', 'Line 2', 'Line 3'], 
         'x': 5, 'y': 5}
    ]
    display.create_slideshow(slideshow_content, duration_per_slide=3.0, 
                            transition=TransitionEffect.FADE)
    time.sleep(15)
    
    # Cleanup
    display.stop_animation()
    display.clear()