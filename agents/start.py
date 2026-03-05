import spade

class DummyAgent(spade.agent.Agent):
    async def setup(self):
        print(f"Hello World! I'm agent {self.jid}")
        
async def main():
    dummy = DummyAgent("dummy@localhost", "password")
    await dummy.start()

if __name__ == "__main__":
    spade.run(main())
