import almasi


class Foo(almasi.Singleton):
	
	def initialize(self):
		print('Foo initilized')

	def run(self):
		print('Running')