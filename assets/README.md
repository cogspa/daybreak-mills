# assets

HDRIs live here. They are not committed — see the repo README for the one-line
curl that fetches the default:

    kloofendal_48d_partly_cloudy_puresky_4k.hdr   20.7 MB, CC0, Poly Haven

Any outdoor `.hdr` or `.exr` works. The Blender pipeline locates the sun by
finding the brightest pixel and inverting Blender's equirectangular mapping, so
it adapts to whatever you drop in here.
