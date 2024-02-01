import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js"


function showImageOnNode(node, name, imageType) {
	const img = new Image();
	img.onload = () => {
		node.imgs = [img];
		app.graph.setDirtyCanvas(true);
	};
	let folder_separator = name.lastIndexOf("/");
	let subfolder = "";
	if (imageType === "temp") {
		subfolder = "";
	} else if (folder_separator > -1) {
		subfolder = name.substring(0, folder_separator);
		name = name.substring(folder_separator + 1);
	}
	img.src = api.apiURL(`/view?filename=${encodeURIComponent(name)}&type=${imageType}&subfolder=${subfolder}${app.getPreviewFormatParam()}${app.getRandParam()}`);
	node.setSizeForImage?.();
}


// Global variables
var uploadByPathNodes = [];  // Used by widget: IMAGEUPLOAD_BYPATH


// Handle Python -> JS messages

function updatePreviewSignalHandle(evt) {
	const name = evt.detail.preview_filename;
	const imageType = evt.detail.preview_type;
	const ogPath = evt.detail.path;

	for (const node of uploadByPathNodes) {
		try {
			let doUpdate = false;
			const pathVals = node.widgets?.filter(w => w.name == "image").map(w => w.getPath());   //map(w => getImagePathFromWidgetValue(w));
			if (pathVals.length >= 1 && pathVals[0] === ogPath) {
				doUpdate = true;
			}
			//doUpdate = true;

			if (doUpdate) {
				console.log("Update preview for node " + node.id);
				showImageOnNode(node, name, imageType);
			}
		} catch (error) { // TODO handle deleted nodes
			console.log(error);
		}
	}
}

api.addEventListener("kap-update-preview", updatePreviewSignalHandle);

// Load image by path
app.registerExtension({
	name: "kap.loadimage.dedup",

	async beforeRegisterNodeDef(nodeType, nodeData, app) {
		if (nodeData?.input?.required?.image?.[1]?.kap_load_image_dedup === true) {
			nodeData.input.required.upload = ["IMAGEUPLOAD_DEDUP"];
		}
		if (nodeData?.input?.required?.image?.[1]?.kap_load_image_by_path === true) {
			nodeData.input.required.upload = ["IMAGEUPLOAD_BYPATH"];
		}
	},

	getCustomWidgets(app) {
		return {
			// Ref: ComfyWidgets.IMAGEUPLOAD (https://github.com/comfyanonymous/ComfyUI/blob/7f4725f6b3f72dd8bdb60dae5dd2c3e943263bcf/web/scripts/widgets.js#L359)
			IMAGEUPLOAD_DEDUP(node, inputName, inputData, app) {
				const imageWidget = node.widgets.find((w) => w.name === (inputData[1]?.widget ?? "image"));

				let uploadWidget;

				function showImage(name) {
					showImageOnNode(node, name, "input");
				}

				var default_value = imageWidget.value;
				Object.defineProperty(imageWidget, "value", {
					set : function(value) {
						this._real_value = value;
					},

					get : function() {
						let value = "";
						if (this._real_value) {
							value = this._real_value;
						} else {
							return default_value;
						}

						if (value.filename) {
							let real_value = value;
							value = "";
							if (real_value.subfolder) {
								value = real_value.subfolder + "/";
							}

							value += real_value.filename;

							if(real_value.type && real_value.type !== "input")
								value += ` [${real_value.type}]`;
						}
						return value;
					}
				});

				// Add our own callback to the combo widget to render an image when it changes
				const cb = node.callback;
				imageWidget.callback = function () {
					showImage(imageWidget.value);
					if (cb) {
						return cb.apply(this, arguments);
					}
				};

				// On load if we have a value then render the image
				// The value isnt set immediately so we need to wait a moment
				// No change callbacks seem to be fired on initial setting of the value
				requestAnimationFrame(() => {
					if (imageWidget.value) {
						showImage(imageWidget.value);
					}
				});

				async function uploadFile(file, updateNode, pasted = false) {
					try {
						// Wrap file in formdata so it includes filename
						const body = new FormData();
						body.append("image", file);
						const overwriteWidget = node.widgets.find(w => w.name === "overwrite_option");
						body.append("overwrite", overwriteWidget.value);
						if (pasted) body.append("subfolder", "pasted");

						const resp = await api.fetchApi("/kap/upload/image-dedup", {
							method: "POST",
							body,
						});

						if (resp.status === 200) {
							const data = await resp.json();
							// Add the file to the dropdown list and update the widget value
							let path = data.name;
							if (data.subfolder) path = data.subfolder + "/" + path;

							if (!imageWidget.options.values.includes(path)) {
								imageWidget.options.values.push(path);
							}

							if (updateNode) {
								showImage(path);
								imageWidget.value = path;
							}
						} else {
							alert(resp.status + " - " + resp.statusText);
						}
					} catch (error) {
						alert(error);
					}
				}

				const fileInput = document.createElement("input");
				Object.assign(fileInput, {
					type: "file",
					accept: "image/jpeg,image/png,image/webp",
					style: "display: none",
					onchange: async () => {
						if (fileInput.files.length) {
							await uploadFile(fileInput.files[0], true);
						}
					},
				});
				document.body.append(fileInput);

				// Create the button widget for selecting the files
				uploadWidget = node.addWidget("button", inputName, "image", () => {
					fileInput.click();
				});
				uploadWidget.label = "choose file to upload";
				uploadWidget.serialize = false;

				// Add handler to check if an image is being dragged over our node
				node.onDragOver = function (e) {
					if (e.dataTransfer && e.dataTransfer.items) {
						const image = [...e.dataTransfer.items].find((f) => f.kind === "file");
						return !!image;
					}

					return false;
				};

				// On drop upload files
				node.onDragDrop = function (e) {
					console.log("onDragDrop called");
					let handled = false;
					for (const file of e.dataTransfer.files) {
						if (file.type.startsWith("image/")) {
							uploadFile(file, !handled); // Dont await these, any order is fine, only update on first one
							handled = true;
						}
					}

					return handled;
				};

				node.pasteFile = function(file) {
					if (file.type.startsWith("image/")) {
						const is_pasted = (file.name === "image.png") &&
										  (file.lastModified - Date.now() < 2000);
						uploadFile(file, true, is_pasted);
						return true;
					}
					return false;
				}

				return { widget: uploadWidget };
			},

			IMAGEUPLOAD_BYPATH(node, inputName, inputData, app) {
				// Widget returned
				let refreshPreviewWidget;

				const imageWidget = node.widgets.find((w) => w.name === (inputData[1]?.widget ?? "image"));

				Object.assign(imageWidget, {  // Better to use Object.defineProperty?
					getPath: function() {
						let path = imageWidget.value;
						if ((path.startsWith('"') && path.endsWith('"')) || (path.startsWith("'") && path.endsWith("'"))) {
							path = path.substring(1, path.length - 1);
						}
						return path;
					},
				});

				var default_value = imageWidget.value;
				Object.defineProperty(imageWidget, "value", {
					set : function(value) {
						this._real_value = value;
					},

					get : function() {
						let value = "";
						if (this._real_value) {
							value = this._real_value;
						} else {
							return default_value;
						}

						if (value.filename) {
							let real_value = value;
							value = "";
							if (real_value.subfolder) {
								value = real_value.subfolder + "/";
							}

							value += real_value.filename;

							if(real_value.type && real_value.type !== "input")
								value += ` [${real_value.type}]`;
						}
						return value;
					}
				});

				// Add our own callback to the string widget to render an image when it changes
				const cb = node.callback;
				imageWidget.callback = function () {
					console.log("image widget (string) callback");
					updateWatchlist({ updateNode: true });
					if (cb) {
						return cb.apply(this, arguments);
					}
				};

				// On load if we have a value then render the image
				// The value isnt set immediately so we need to wait a moment
				// No change callbacks seem to be fired on initial setting of the value
				requestAnimationFrame(() => {
					if (imageWidget.value) {
						//showImageOnNode(node, imageWidget.value);
						updateWatchlist({ updateNode: true });
					}
				});

				async function updatePreview() {
					const body = new FormData();
					body.append("image_path", imageWidget.getPath());
					const resp = await api.fetchApi("/kap/upload/update-preview", {
						method: "POST",
						body,
					});
					
					if (resp.status === 200) {
						const data = await resp.json();
						const previewName = data.preview_filename;
						const previewImageType = data.preview_image_type;
						showImageOnNode(node, previewName, previewImageType);
					}
				}

				async function updateWatchlist({ updateNode = true }) {
					try {
						// Watchlist consists of images from all loadbypath widgets, and the first item is the path of the image in the current node
						const allImagePaths = [];
						allImagePaths.push(imageWidget.getPath());
						for (const nd of uploadByPathNodes) {
							if (nd.id === node.id)
								continue;
							const pathVals = nd.widgets?.filter(w => w.name == "image").map(w => w.getPath());
							if (pathVals.length >= 1) {
								allImagePaths.push(pathVals[0]);
							}
						}

						const body = new FormData();
						body.append("all_image_paths", JSON.stringify(allImagePaths));

						const resp = await api.fetchApi("/kap/upload/update-watchlist", {
							method: "POST",
							body,
						});

						if (resp.status === 200) {
							const data = await resp.json();
							// We are only updating for the image in the current node, which is the first item
							if (data.success[0]) {
								const previewName = data.preview_names[0];

								if (updateNode) {
									showImageOnNode(node, previewName, data.preview_images_type);
								}
							} else {
								// TODO Display error more elegantly
								alert(`Generating preview for '${imageWidget.getPath()}' was not successful (node id: ${node.id})`);
							}

						} else {
							alert(resp.status + " - " + resp.statusText);
						}
					} catch (error) {
						alert(error);
					}
				}

				// NOT POSSIBLE TO READ FILEPATHS IN JS https://stackoverflow.com/questions/15201071/how-to-get-full-path-of-selected-file-on-change-of-input-type-file-using-jav 
				//const fileInput = document.createElement("input");
				//Object.assign(fileInput, {
				//	type: "file",
				//	accept: "image/jpeg,image/png,image/webp",
				//	style: "display: none",
				//	onchange: async () => {
				//		if (fileInput.files.length) {
				//			await uploadPath(fileInput.files[0], true);
				//		}
				//	},
				//});
				//document.body.append(fileInput);

				// Create the button widget for selecting the files
				//uploadWidget = node.addWidget("button", inputName, "image", () => {
				//	fileInput.click();
				//});
				//uploadWidget.label = "choose file to upload";
				//uploadWidget.serialize = false;

				// Refresh preview button widget
				refreshPreviewWidget = node.addWidget("button", null, null, () => {
					updatePreview();
				});
				refreshPreviewWidget.label = "refresh preview";
				refreshPreviewWidget.serialize = false;

				// Add handler to check if an image is being dragged over our node
				//node.onDragOver = function (e) {
				//	if (e.dataTransfer && e.dataTransfer.items) {
				//		const image = [...e.dataTransfer.items].find((f) => f.kind === "file");
				//		return !!image;
				//	}

				//	return false;
				//};

				//// On drop upload files
				//node.onDragDrop = function (e) {
				//	console.log("onDragDrop called");
				//	let handled = false;
				//	for (const file of e.dataTransfer.files) {
				//		if (file.type.startsWith("image/")) {
				//			uploadPath(file, !handled); // Dont await these, any order is fine, only update on first one
				//			handled = true;
				//		}
				//	}

				//	return handled;
				//};

				//node.pasteFile = function(file) {
				//	if (file.type.startsWith("image/")) {
				//		const is_pasted = (file.name === "image.png") &&
				//						  (file.lastModified - Date.now() < 2000);
				//		uploadPath(file, true, is_pasted);
				//		return true;
				//	}
				//	return false;
				//}

				uploadByPathNodes.push(node);

				return { widget: refreshPreviewWidget };
			},
		};
	},
});

