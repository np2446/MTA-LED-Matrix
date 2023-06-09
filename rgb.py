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
        self.matrix = RGBMatrix(options = self.options)

        # initialize fonts and canvas
        fontPath = "/home/noah/MTAGRBMatrix/eight-bit-dragon.otf" # replace with font path
        self.font = ImageFont.truetype(fontPath, size=24)
        self.canvas = Image.new("RGB", (self.options.cols, self.options.rows))
        self.draw = ImageDraw.Draw(self.canvas)

    def displayText(self, text):
        self.matrix.Clear()
        text_width, text_height = self.draw.textsize(text, font=self.font)
        x = self.options.cols
        y = 4

        while x > -text_width:
            self.canvas = Image.new("RGB", (self.options.cols, self.options.rows))
            self.draw = ImageDraw.Draw(self.canvas)
            self.draw.text((x, y), text, font=self.font, fill=(255, 255, 0))
            self.matrix.SetImage(self.canvas.convert('RGB'))
            self.matrix.SwapOnVSync()
            x -= 1  # Adjust the scrolling speed here

    





