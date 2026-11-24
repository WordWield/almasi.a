from almasi import a


class Foo(a.Singleton):
	
	def initialize(self):
		print('Foo initilized')

	def run(self):
		print('Running')