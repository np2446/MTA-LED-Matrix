from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import ImageFont, ImageDraw, Image

class MatrixClass():

    def __init__(self):
        # initialize matrix options and matrix object
        self.options = RGBMatrixOptions()
        self.options.rows = 32
        self.options.cols = 64
        self.options.chain_length = 1
        self.options.parallel = 1
        self.options.hardware_mapping = 'adafruit-hat'
        self.options.gpio_slowdown = 2
        self.matrix = RGBMatrix(options = self.options)

        # initialize fonts and canvas
        fontPath = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"   
        self.font = ImageFont.truetype(fontPath, size=12)
        self.canvas = Image.new("RGB", (self.options.cols, self.options.rows))
        self.draw = ImageDraw.Draw(self.canvas)

    def staticText(self, text):
        self.matrix.Clear()
        self.canvas = Image.new("RGB", (self.options.cols, self.options.rows))
        self.draw = ImageDraw.Draw(self.canvas)
        self.draw.text((0, 0), text, font=self.font, fill=(255, 0, 0))
        self.matrix.SetImage(self.canvas.convert('RGB'))

    def displayText(self, text1, text2):
        self.matrix.Clear()
        text_width1, text_height = self.draw.textsize(text1, font=self.font)
        twidth2, theight2 = self.draw.textsize(text2, font=self.font)
        text_width = max(text_width1, twidth2)
        x = self.options.cols
        y1 = 0
        y2 = 17

        while x > -text_width:
            self.canvas = Image.new("RGB", (self.options.cols, self.options.rows))
            self.draw = ImageDraw.Draw(self.canvas)
            self.draw.text((x, y1), text1, font=self.font, fill=(255, 255, 0))
            self.draw.text((x,y2), text2, font=self.font, fill=(255,0,0))
            self.matrix.SetImage(self.canvas.convert('RGB'))
            x -= 0.35  # Adjust the scrolling speed here

"""    
    def displayTextRed(self, text):
        self.matrix.Clear()
        text_width, text_height = self.draw.textsize(text, font=self.font)
        x = self.options.cols
        y = 2

        while x > -text_width:
            self.canvas = Image.new("RGB", (self.options.cols, self.options.row>
            self.draw = ImageDraw.Draw(self.canvas)
            self.draw.text((x, y), text, font=self.font, fill=(255, 0, 0))
            self.matrix.SetImage(self.canvas.convert('RGB'))
            x -= 0.35  # Adjust the scrolling speed here

"""


