
# protongdb
## A small little helper for running games with Proton and debugging with GDB

## Requirements

 - At least Python 3.5
 - [protontricks](https://github.com/Matoking/protontricks) pip package and its dependencies (`pip install --user protontricks`)

## Usage

The basic usage is as follows:

On any Steam app that you have a prefix for (ie. started the game at least once) you can use
```
protongdb <appid>
```
to start it with a debugger.

You can find the appid for the game using the Properties > Updates tab of the game.

If the game crashes or you hit a breakpoint, you can run `wine-reload` to resolve any symbols, etc.

You can then get a backtrace or step-through the code like a native app.

## Special Thanks

Thanks to the creators of [protontricks](https://github.com/Matoking/protontricks) as it had a lot of useful helper functions to make this work, and [Rémi Bernon](https://github.com/rbernon) for the WineReload code.

